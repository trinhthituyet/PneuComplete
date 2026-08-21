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
    ("main_line_port_size", "Cỡ cửa đường trục chính (FRL)",
     "Cỡ FRL theo tổng lưu lượng, nhưng catalog chỉ cho lưu lượng dạng đồ thị."),
    ("frl_size", "Cỡ AC (10/20/25/30/40)",
     "Một cỡ cửa có ở nhiều cỡ AC — engine liệt kê ứng viên, bạn chọn."),
    ("valve_series_size", "Cỡ van (SY3000/SY5000/SY7000)",
     "Phụ thuộc lưu lượng cần thiết; engine chưa trích được Cv từ catalog."),
    ("valve_function", "Loại van mặc định",
     "Phụ thuộc CHỨC NĂNG từng cơ cấu — khai riêng cho từng xy-lanh ở bảng bên trên."),
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
    """Mã hàng gợi ý cho một nhóm thiết bị — đọc từ DB, KHÔNG hard-code.

    Lấy các mã đã có trong bảng `part` thuộc đúng layer của nhóm. Chỉ là GỢI Ý:
    người dùng vẫn gõ mã tự do được, và /api/parse mới là chỗ kiểm.
    """
    layer = (G.GROUPS.get(group) or {}).get("layer")
    if not layer:
        return {"codes": []}
    # part không mang layer, nên lần theo series → catalog_id của các họ đã biết
    rows = con.execute(
        """select distinct p.part_number from part p
           join series s on s.id = p.series_id
           where exists (select 1 from code_slot cs where cs.series_id = s.id)
           order by p.part_number limit 400""").fetchall()
    want = {"actuator": ("CDM2", "CM2", "MGP", "CDQS", "CQS", "CDG", "CJ2", "MHZ"),
            "valve": ("SY", "SS5Y", "VT"),
            "air_prep": ("AC", "AR", "AF", "AW"),
            "accessory": ("AS",),
            "piping": ("TU", "KQ2", "KSL"),
            "electrical": ("D-M9", "ISE", "ZS"),
            }.get(layer, ())
    out = [r["part_number"] for r in rows
           if not want or r["part_number"].upper().startswith(want)]
    return {"codes": out[:60], "layer": layer}


def api_parse(con, code):
    if not code:
        return {"ok": False, "error": "thiếu mã"}
    r = P.parse(con, code)
    return {"ok": bool(r.get("ok")), "series": r.get("series"),
            "series_name": r.get("series_name"), "attrs": r.get("attrs"),
            "trace": [{"slot": t[0], "code": t[1], "label": t[2]} for t in r.get("trace", [])],
            "unparsed": r.get("unparsed"), "missing": r.get("missing"),
            "error": r.get("error")}


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
    problems = T.validate(root)
    root, fixed = T.normalize(root)
    gr = T.to_graph(root)

    res = api_bom_graph(con, payload, gr, tree=root)
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
    res["warnings"] = warns
    res["tree"] = root
    res["tree_fixed"] = fixed
    return res


def api_bom_graph(con, payload, gr, tree=None):
    res_g = G.resolve(con, gr)
    if not res_g["inputs"] and not res_g["manual_lines"]:
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
    if tree is not None:
        # điền mã vào chính CÂY (nguồn sự thật khi nhập bằng cây), rồi lưu cây
        for n, _, _ in T.walk(tree):
            f = fill.get(n.get("id"))
            if f and not n.get("code"):
                n["code"] = f["code"]
                n["filled_by_bom"] = True
        T.save(con, res["project_id"], tree)
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
    rows = con.execute(
        """select po.layer, po.proposed_code, po.qty, po.rule_code, po.rationale,
                  po.confidence, po.status
           from project_output po where po.project_id=? order by po.layer, po.id""",
        (project_id,)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Tầng", "Mã hàng", "Số lượng", "Luật", "Độ tin cậy", "Trạng thái", "Lý do"])
    for r in rows:
        w.writerow([r["layer"], r["proposed_code"] or "", r["qty"], r["rule_code"] or "",
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
                self._send(200, {"graph": G.load(con, pid), "tree": T.load(con, pid)})
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
