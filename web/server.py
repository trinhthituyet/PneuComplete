"""Web UI cho PneuComplete — chỉ dùng stdlib (http.server), không cần FastAPI.

    python3 -m web.server            # http://localhost:8765
    python3 -m web.server --port 9000

Vì sao stdlib: môi trường này không cài được package từ PyPI (bị chặn), mà toàn bộ
project cũng đã theo hướng không phụ thuộc — crawler dùng urllib, đọc xlsx bằng
zipfile, đọc PDF bằng pdftotext. Giữ nguyên hướng đó.

API:
    GET  /                     trang chính
    GET  /api/series           danh sách series có ngữ pháp (để gợi ý nhập)
    GET  /api/parse?code=X     parse 1 mã hàng — kiểm tra ngay khi đang nhập
    POST /api/bom              {inputs, config} → BOM + cảnh báo + gap
    GET  /api/csv?project=N    xuất BOM ra CSV
    GET  /api/defaults         cấu hình mặc định + danh sách khoá cần khai
    GET  /api/groups           nhóm thiết bị + cổng mặc định (cho palette canvas)
    GET  /api/ports?code=X&group=Y  cổng THẬT của một mã hàng
    GET  /api/codes?group=X    mã hàng gợi ý cho một nhóm (đọc DB, không hard-code)
    POST /api/classify         {code, tree} → loại thiết bị + chỗ gắn được
    POST /api/move             {tree, node, parent} → chuyển thiết bị sang cha khác
    GET  /api/graph?project=N  đọc lại sơ đồ đã lưu
    POST /api/bom              nhận CẢ HAI: {inputs,config} phẳng, hoặc {graph,config}

Cờ dòng lệnh:
    --port N        cổng, mặc định 8765
    --host ADDR     địa chỉ bind. Mặc định 127.0.0.1 = CHỈ máy này truy cập được.
                    Trong Docker phải là 0.0.0.0, nếu không thì host không vào được
                    container (bind 127.0.0.1 bên trong container chỉ nghe loopback
                    CỦA container). Biến môi trường PNEU_HOST cũng đặt được.
"""
import csv
import io
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import db                      # noqa: E402
from engine import bom                      # noqa: E402
from engine import classify as CL           # noqa: E402
from engine import graph as G               # noqa: E402
from engine import materialize              # noqa: E402
from engine import parser as P              # noqa: E402
from engine import tree as T                # noqa: E402

HERE = Path(__file__).resolve().parent

# Khoá cấu hình engine KHÔNG suy được — UI phải hiển thị rõ để người dùng khai.
# Mỗi khoá kèm nhãn tiếng Việt và lý do, lấy từ rationale của luật tương ứng.
NEEDS_INPUT = [
    ("tube_total_m", "Tổng mét ống cho cả máy",
     "Phụ thuộc layout máy, khoảng cách tủ van tới từng xy-lanh. Engine không suy được."),
    ("supply_pressure_mpa", "Áp nguồn của xưởng (MPa)",
     "Áp khí máy nén cấp vào FRL. Engine cần nó để chọn cỡ AC: đồ thị catalog có "
     "hai họ đường theo áp vào (0,7 và 1,0 MPa) cho số khác nhau, mà không điều "
     "áp LÊN được nên áp vào phải ≤ áp nguồn. Catalog không có thông số này."),
    ("fitting_points", "Điểm nối ống → ren (kiểu · cỡ ống · cỡ ren · số lượng)",
     "Engine KHÔNG suy được SỐ LƯỢNG đầu nối: đo trên hai máy thật, tỉ lệ cút vuông "
     "trên mỗi thiết bị là 1,42 và 2,74 — chênh gấp đôi. Van dùng cửa one-touch và "
     "tiết lưu AS…F đã có one-touch sẵn nên đoạn van↔xy-lanh không cần đầu nối rời; "
     "toàn bộ đầu nối thuộc mạng phân phối khí mà engine không thấy cách đi ống. "
     "Bạn khai điểm nối, engine chọn ĐÚNG MÃ và chặn tổ hợp không tồn tại."),
    ("manifold_type", "Kiểu manifold",
     "Type 20 và Type 20P dùng end plate khác nhau; chọn sai thì không lắp được."),
    # Ba khoá SỞ THÍCH — nhiều phương án đều lắp được nên engine không tự chọn,
    # nhưng chỉ hỏi MỘT LẦN cho cả dự án, không hỏi từng thiết bị.
    ("valve_piping", "Cửa van: one-touch hay ren",
     "Cắm ống trực tiếp (C6/C8) hay vặn đầu nối vào ren (01/02) — tuỳ cách bạn đi ống."),
    ("fitting_shape", "Kiểu đầu nối",
     "Thẳng · vuông (chữ L) · T. Cùng lắp được, chọn theo chỗ hẹp/rộng của máy."),
    ("exhaust_silencer", "Gắn giảm âm cửa xả",
     "Trên manifold xả là chung nên chỉ cần 1–2 cái, không phải mỗi van một cái."),
]


def api_series(con):
    rows = con.execute(
        """select s.id, s.code, s.catalog_id, s.name, s.part_prefix,
                  (select count(*) from code_slot cs where cs.series_id=s.id) slots
           from series s
           where exists (select 1 from code_slot cs where cs.series_id=s.id)
           order by s.code""").fetchall()
    return [dict(r) for r in rows]


# Khoá engine TỰ TÍNH — UI hiện kết quả kèm cách tính, có ô ghi đè, KHÔNG hỏi.
# Trước đây hai khoá này nằm trong NEEDS_INPUT nên UI vẫn bắt chọn dù engine đã
# tính xong từ §10.2 — người dùng thấy ô trống thì tưởng bắt buộc phải điền.
ENGINE_COMPUTED = [
    ("valve_series_size", "Cỡ van",
     "Tính từ tổng lưu lượng cần cấp, tra bảng dẫn nạp âm C của catalog SY."),
    ("valve_function", "Loại van",
     "Suy theo tác động của TỪNG xy-lanh: kép → 5/2, đơn → 3/2. "
     "Cần dừng giữa hành trình thì đổi ở node van."),
    ("main_line_port_size", "Cỡ cửa đường trục chính (FRL)",
     "Đi kèm cỡ AC, không phải câu hỏi riêng: đồ thị lưu lượng được ĐO Ở một cỡ "
     "cửa xác định, nên khi engine dùng đường cong đó để chọn cỡ thân thì cửa đã "
     "bị quyết định theo. Khai cửa nhỏ hơn thì engine cảnh báo số lưu lượng là "
     "lạc quan; khai cửa quá lớn so với thân thì cảnh báo cặp đó có thể không có."),
    ("frl_size", "Cỡ AC",
     "Tính từ tổng lưu lượng + áp nguồn, tra đồ thị lưu lượng→áp ra của catalog "
     "FRL đã số hoá (db/seed/charts/ac-flow.yaml). Đặt điều áp lên bậc kế tiếp "
     "trên áp làm việc rồi chọn cỡ nhỏ nhất còn giữ đủ áp ở lưu lượng đó."),
]


def api_groups():
    """Nhóm thiết bị cho palette. UI KHÔNG hard-code danh sách này."""
    return {
        "groups": [{"key": k, "label": v["label"], "layer": v["layer"],
                    "is_actuator": bool(v.get("is_actuator")),
                    "ports": v["ports"]}
                   for k, v in G.GROUPS.items()],
        "edge_kinds": [{"key": k, "label": v} for k, v in G.EDGE_KINDS.items()],
        # cặp nhóm → loại cạnh mặc định, để UI không phải hỏi mỗi lần vẽ dây
        "default_edge_kind": [{"from": a, "to": b, "kind": k}
                              for (a, b), k in G.DEFAULT_EDGE_KIND.items()],
        # Quy tắc cha–con để UI biết loại nào thêm được vào đâu. UI KHÔNG
        # hard-code danh sách này — thêm họ thiết bị mới chỉ sửa engine/tree.py.
        "parent_of": {k: {"allowed": [a for a in v[0]], "why": v[1]}
                      for k, v in T.PARENT_OF.items()},
        "singleton": list(T.SINGLETON),
    }


def api_ports(con, code, group):
    """Cổng thật của một mã. Gọi sau khi /api/parse thành công."""
    return {"ports": G.ports_for(con, code, group, materialize.load_templates())}


def api_codes(con, group):
    """Mã hàng gợi ý cho một LOẠI thiết bị — lọc theo bảng phân loại, không theo
    tiền tố mã.

    ĐÃ SỬA: bản trước lọc bằng danh sách tiền tố viết tay theo `layer`
    ({"valve": ("SY","SS5Y","VT"), …}). Hai chỗ sai:
      · layer gộp nhiều loại, nên chọn "Đế manifold" vẫn nhận cả mã VAN SY5220 —
        đúng thứ vừa phải sửa ở fill_codes().
      · SY5000-GS-1 (gasket) khớp tiền tố 'SY' nên hiện trong danh sách van.
    Giờ dùng engine/classify.py: mã nào phân loại ra ĐÚNG loại này thì mới hiện.
    Vẫn chỉ là GỢI Ý — người dùng gõ mã tự do được, /api/classify mới là chỗ kiểm.
    """
    if group not in G.GROUPS:
        return {"codes": []}
    rows = con.execute(
        """select distinct p.part_number from part p
           join series s on s.id = p.series_id
           where exists (select 1 from code_slot cs where cs.series_id = s.id)
           order by p.part_number limit 800""").fetchall()
    out = []
    for r in rows:
        pn = r["part_number"]
        if not pn:
            continue
        c = CL.classify(con, pn)
        if c.get("ok") and c["node_type"] == group:
            out.append(pn)
        if len(out) >= 60:
            break
    return {"codes": out, "layer": (G.GROUPS[group] or {}).get("layer")}


def api_classify(con, code, tree=None):
    """Gõ MÃ → loại thiết bị + chỗ gắn được. Yêu cầu (2) của bạn.

    Trả kèm `placements` (các node trong cây nhận được nó làm con) để UI khỏi bắt
    người dùng tự dò xem đặt được ở đâu.
    """
    r = CL.classify(con, code)
    if r.get("ok") and tree:
        r["placements"] = [{"id": i, "label": l}
                           for i, l in CL.placements(tree, r["node_type"])]
    return r


def api_parse(con, code):
    if not code:
        return {"ok": False, "error": "thiếu mã"}
    r = P.parse(con, code)
    return {"ok": bool(r.get("ok")), "series": r.get("series"),
            "series_name": r.get("series_name"), "attrs": r.get("attrs"),
            "trace": [{"slot": t[0], "code": t[1], "label": t[2]} for t in r.get("trace", [])],
            "unparsed": r.get("unparsed"), "missing": r.get("missing"),
            "error": r.get("error")}


def api_move(payload):
    """Chuyển thiết bị sang cha khác. Yêu cầu (4): thêm/bớt ở BẤT KỲ vị trí.

    Làm ở SERVER dù UI đã có bảng PARENT_OF: luật "không chuyển vào con cháu của
    chính nó" là chỗ mất dữ liệu im lặng (cả nhánh rời khỏi cây), nên chỉ nên có
    MỘT bản thực thi. Chuyển chỗ là thao tác thưa, thêm một lượt gọi không đáng lo.
    """
    tree = payload.get("tree")
    if not tree:
        return {"ok": False, "problem": {"what": "chưa có cây", "fix": "", "detail": ""}}
    ok, pb = T.move(tree, payload.get("node"), payload.get("parent"))
    return {"ok": ok, "problem": pb, "tree": tree if ok else None}


def api_bom(con, payload):
    """Nhận payload PHẲNG (cũ) hoặc ĐỒ THỊ (mới).

    Giữ tương thích ngược là có chủ đích: bảng phẳng vẫn là cách nhập nhanh nhiều
    xy-lanh (mục 4 của tài liệu yêu cầu), không bỏ.
    """
    tr = payload.get("tree")
    if tr:
        return api_bom_tree(con, payload, tr)
    gr = payload.get("graph")
    if gr:
        return api_bom_graph(con, payload, gr)

    inputs = []
    for it in payload.get("inputs", []):
        code = (it.get("code") or "").strip()
        if not code:
            continue
        qty = int(it.get("qty") or 1)
        over = {k: v for k, v in (it.get("overrides") or {}).items()
                if v not in (None, "", "auto")}
        inputs.append((code, qty, over))
    if not inputs:
        return {"error": "chưa nhập actuator nào"}

    cfg = _clean_config(payload.get("config") or {})

    bom.seed_rules(con)
    res = bom.build(con, inputs, cfg, project_name=payload.get("name") or "web")
    return {
        "project_id": res["project_id"],
        "project": {k: v for k, v in res["project"].items()},
        "calc": res["calc"], "system": res["system"],
        "lines": res["lines"], "warnings": res["warnings"], "gaps": res["gaps"],
    }


def api_bom_tree(con, payload, root):
    """Dựng BOM từ CÂY dự án. Cây là cách nhập chính, thay canvas kéo dây.

    Ba bước, thứ tự có lý do:
      1. validate  — báo chỗ đặt sai, KHÔNG sửa
      2. normalize — dịch về đúng cha, và NÓI RA đã dịch gì
      3. to_graph  — dịch cha–con thành cạnh để dùng lại nguyên resolver đã có
    """
    # Bỏ phụ kiện lần dựng trước TRƯỚC khi làm gì khác — nếu giữ thì số lượng
    # cộng dồn qua mỗi lần bấm Dựng BOM.
    T.drop_generated(root)
    problems = T.validate(root)
    # normalize PHẢI biết liên kết: không thì nó dịch thiết bị về cha đầu tiên gặp
    # được, trái với liên kết bạn vừa khai. Nên lọc liên kết trước khi normalize.
    links, dropped = T.prune_links(root, payload.get("links") or [])
    root, fixed = T.normalize(root, links)

    # XOÁ mã do ENGINE điền ở lần dựng trước, giữ mã BẠN gõ.
    #
    # LỖI ĐÃ MẮC: fill_codes() bỏ qua mọi node "đã có mã", không phân biệt nguồn.
    # Nên dựng BOM với 1 trạm → engine điền SY3220 (SY3000, đủ cho 1 xy-lanh);
    # thêm trạm 2,3,4 rồi dựng lại → lưu lượng tăng, các trạm mới nhận SY5220
    # (SY5000) nhưng trạm 1 GIỮ NGUYÊN SY3220 → van trạm 1 THIẾU CỠ, và cả máy
    # lẫn lộn hai cỡ van trên cùng manifold.
    #
    # Quyết định do engine suy phải được TÍNH LẠI mỗi lần, vì đầu vào đã đổi.
    # Chỉ giá trị người dùng gõ mới được giữ.
    # `filled_by_bom` lưu CHÍNH GIÁ TRỊ engine đã điền, không phải cờ true/false.
    # Nhờ vậy so được: code còn khớp giá trị đó ⇒ chưa ai sửa ⇒ tính lại được.
    # Code đã khác ⇒ người dùng đã gõ đè ⇒ GIỮ.
    # Dùng cờ boolean thì hễ UI quên xoá cờ là mất giá trị người dùng nhập —
    # đúng lỗi vừa mắc.
    for n, _, _ in T.walk(root):
        prev = n.get("filled_by_bom")
        if prev and n.get("code") == prev:
            n["code"] = ""
            n.pop("filled_by_bom", None)
        elif prev:
            n.pop("filled_by_bom", None)     # người dùng đã đè → quên dấu cũ đi

    # Liên kết đã lọc ở trên (trước normalize). Kiểm miền tín hiệu ở đây, sau khi
    # cây đã về đúng dạng cuối.
    link_problems = T.validate_links(root, links)

    gr = T.to_graph(root, links)

    res = api_bom_graph(con, payload, gr, tree=root, links=links)
    if res.get("error"):
        return res

    warns = list(res.get("warnings") or [])
    for pb in problems:
        warns.append({**pb, "code": pb["rule_code"],
                      "message": pb["what"], "rationale": pb.get("detail") or ""})
    if fixed:
        warns.append({
            "severity": "info", "code": "TREE_NORMALIZED", "rule_code": "T-PARENT-01",
            "what": f"đã dịch {len(fixed)} thiết bị về đúng cha",
            "message": "Đã dịch về đúng cha: " + " · ".join(fixed),
            "fix": "Kiểm lại cây bên trái", "rationale": "",
            "detail": "\n".join(fixed)})
    for pb in link_problems:
        warns.append({**pb, "code": pb["rule_code"], "message": pb["what"],
                      "rationale": pb.get("detail") or ""})
    if dropped:
        warns.append({
            "severity": "info", "code": "LINKS_PRUNED", "rule_code": "T-LINK-01",
            "what": f"đã bỏ {len(dropped)} liên kết trỏ tới thiết bị đã xoá",
            "message": "Đã bỏ liên kết tới thiết bị đã xoá: " + " · ".join(dropped),
            "fix": "Nối lại nếu cần", "rationale": "", "detail": "\n".join(dropped)})
    res["warnings"] = warns
    res["tree"] = root
    res["links"] = links
    res["tree_fixed"] = fixed
    return res


def api_bom_graph(con, payload, gr, tree=None, links=None):
    res_g = G.resolve(con, gr)
    if not res_g["inputs"] and not res_g["manual_lines"] and not res_g["own_lines"]:
        return {"error": "sơ đồ chưa có thiết bị nào dựng được BOM "
                         "(cần ít nhất 1 node xy-lanh có mã, hoặc 1 node tự do)"}

    cfg = _clean_config(payload.get("config") or {})
    # config_extra (vd điện áp lấy từ node PLC) là SUY LUẬN, nên xếp DƯỚI cấu hình
    # người dùng khai tay — cùng nguyên tắc với thứ tự ưu tiên trong bom.build().
    cfg = {**res_g["config_extra"], **cfg}

    bom.seed_rules(con)
    res = bom.build(con, res_g["inputs"], cfg,
                    project_name=payload.get("name") or "graph") \
        if res_g["inputs"] else _empty_result(con, cfg, payload)

    lines = list(res["lines"]) + res_g["manual_lines"]
    # Thiết bị bạn tự thêm trên sơ đồ. BỎ dòng mà engine ĐÃ đề xuất đúng mã đó:
    # dòng của engine có luật, lý do và số lượng tính được, nên nó thắng — nếu
    # không thì mỗi lần dựng lại sẽ có hai dòng cùng mã (một do engine điền vào
    # node ở lần trước, một do node đó giờ có mã).
    have = {l.get("part_number") for l in lines}
    extra = [l for l in res_g.get("own_lines") or [] if l["part_number"] not in have]
    lines += extra
    # Ghi vào DB những dòng cộng thêm SAU build(): thiết bị bạn tự thêm và dòng
    # 'Mã tự do'. Không ghi thì CSV xuất ra thiếu đúng những thứ đó — UI đọc `lines`
    # trả về nên vẫn thấy, còn CSV đọc project_output nên không.
    if extra or res_g["manual_lines"]:
        bom.save_lines(con, res["project_id"], extra + res_g["manual_lines"])
    warnings = list(res["warnings"]) + res_g["warnings"]

    # Mục 5 của spec: điền mã hàng ngược lại vào sơ đồ → as-built diagram.
    # Ghi luôn mã đã điền vào graph rồi mới lưu, để mở lại project cũ là thấy sơ đồ
    # đã có mã, không phải dựng lại BOM.
    fill = G.fill_codes(gr, lines)
    for n in gr.get("nodes") or []:
        f = fill.get(n.get("id"))
        if f:
            n["code"] = f["code"]
            n["filled_by_bom"] = True
    # Nửa còn lại: node có trên sơ đồ mà không dòng nào đại diện → vào BOM với mã
    # để trống. Phải làm SAU fill_codes (mã vừa điền tính là đã đại diện) và TRƯỚC
    # attach_lines (để chính node đó được đánh dấu 'chưa có mã' trên sơ đồ).
    lines += G.uncovered_lines(gr, lines, fill)
    if tree is not None:
        # điền mã vào chính CÂY (nguồn sự thật khi nhập bằng cây), rồi lưu cây
        for n, _, _ in T.walk(tree):
            f = fill.get(n.get("id"))
            if f and not n.get("code"):
                n["code"] = f["code"]
                n["filled_by_bom"] = f["code"]      # lưu GIÁ TRỊ, không phải cờ
        # (1) treo phụ kiện engine sinh vào đúng node cha → cây, bảng BOM và sơ
        # đồ cùng thấy quan hệ mẹ–con.
        T.attach_lines(tree, lines)
        T.save(con, res["project_id"], tree, links)
    else:
        G.save(con, res["project_id"], gr)
    return {
        "project_id": res["project_id"],
        "project": {k: v for k, v in res["project"].items()},
        "calc": res["calc"], "system": res["system"],
        "lines": lines, "warnings": warnings, "gaps": res["gaps"],
        "graph_info": res_g["info"], "fill": fill,
    }


def _empty_result(con, cfg, payload):
    """Sơ đồ chỉ có node tự do: vẫn tạo project để lưu sơ đồ và xuất CSV được."""
    cur = con.execute("insert into project (name, config) values (?,?)",
                      (payload.get("name") or "graph",
                       json.dumps(cfg, ensure_ascii=False)))
    con.commit()
    return {"project_id": cur.lastrowid, "project": cfg, "calc": [], "system": {},
            "lines": [], "warnings": [], "gaps": []}


def _clean_config(raw):
    cfg = {}
    for k, v in raw.items():
        if v in (None, "", "auto"):
            continue
        if k in ("tube_total_m", "tube_od_mm", "tube_roll_length_m",
                 "pressure_mpa", "cycle_s", "safety_factor"):
            cfg[k] = float(v)
        elif k in ("use_manifold", "frl_lubricator", "frl_mist_separator", "automation"):
            cfg[k] = v in (True, "true", "1", "co", "có")
        else:
            cfg[k] = v
    return cfg


def api_csv(con, project_id):
    """BOM → CSV. Cột VẬT TƯ để dòng chưa có mã vẫn đọc được là cái gì.

    Không có cột đó thì dòng thiếu mã xuất ra chỉ còn ô trống — người nhận CSV
    không biết đang thiếu bộ AC hay thiếu ống.
    """
    rows = con.execute(
        """select po.layer, po.proposed_code, po.qty, po.rule_code, po.rationale,
                  po.confidence, po.status, po.requirement
           from project_output po where po.project_id=? order by po.layer, po.id""",
        (project_id,)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Tầng", "Mã hàng", "Vật tư", "Số lượng", "Luật", "Độ tin cậy",
                "Trạng thái", "Lý do"])
    for r in rows:
        item = ""
        if r["status"] == "gap" and r["requirement"]:
            try:
                item = (json.loads(r["requirement"]) or {}).get("item") or ""
            except (ValueError, TypeError):
                item = ""
        w.writerow([r["layer"], r["proposed_code"] or "", item, r["qty"],
                    r["rule_code"] or "",
                    f"{r['confidence']:.0%}" if r["confidence"] else "",
                    r["status"], (r["rationale"] or "").replace("\n", " ")])
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "PneuComplete/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str)
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        con = db.connect()
        try:
            if u.path in ("/", "/index.html"):
                self._send(200, (HERE / "index.html").read_bytes(),
                           "text/html; charset=utf-8")
            elif u.path == "/api/series":
                self._send(200, api_series(con))
            elif u.path == "/api/defaults":
                self._send(200, {"defaults": bom.DEFAULT_PROJECT,
                                 "needs_input": [{"key": k, "label": l, "why": w}
                                                 for k, l, w in NEEDS_INPUT],
                                 "computed": [{"key": k, "label": l, "why": w}
                                              for k, l, w in ENGINE_COMPUTED],
                                 "valve_functions": list(bom.VALVE_FUNCTION)})
            elif u.path == "/api/groups":
                self._send(200, api_groups())
            elif u.path == "/api/codes":
                self._send(200, api_codes(con, (q.get("group") or [""])[0]))
            elif u.path == "/api/ports":
                self._send(200, api_ports(con, (q.get("code") or [""])[0],
                                          (q.get("group") or ["custom"])[0]))
            elif u.path == "/api/graph":
                pid = int((q.get("project") or ["0"])[0])
                self._send(200, {"graph": G.load(con, pid), "tree": T.load(con, pid),
                                 "links": T.load_links(con, pid)})
            elif u.path == "/api/parse":
                self._send(200, api_parse(con, (q.get("code") or [""])[0]))
            elif u.path == "/api/csv":
                pid = int((q.get("project") or ["0"])[0])
                self._send(200, api_csv(con, pid), "text/csv; charset=utf-8")
            else:
                self._send(404, {"error": "không có đường dẫn này"})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            con.close()

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        con = db.connect()
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
            if u.path == "/api/bom":
                self._send(200, api_bom(con, payload))
            elif u.path == "/api/move":
                self._send(200, api_move(payload))
            elif u.path == "/api/classify":
                # POST vì cần gửi kèm CÂY để trả về chỗ gắn được. GET thì cây phải
                # nhồi vào query string.
                self._send(200, api_classify(con, payload.get("code"),
                                             payload.get("tree")))
            else:
                self._send(404, {"error": "không có đường dẫn này"})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            con.close()


def main(argv):
    port = int(os.environ.get("PNEU_PORT") or 8765)
    host = os.environ.get("PNEU_HOST") or "127.0.0.1"
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--host" in argv:
        host = argv[argv.index("--host") + 1]
    srv = ThreadingHTTPServer((host, port), Handler)
    where = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"PneuComplete UI → http://{where}:{port}   (bind {host})")
    print("  Ctrl-C để dừng")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ndừng")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
