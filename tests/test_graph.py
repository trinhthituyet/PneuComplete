"""Test đồ thị đấu nối — gồm TEST CASE CHẤP NHẬN ở mục 8 của tài liệu yêu cầu.

    python3 tests/test_graph.py

Mục 8 yêu cầu dựng lại đúng cấu trúc sơ đồ CAD: 8 cụm van+xy-lanh nối chung tới
1 Filter Regulator, và kiểm 4 điều. Test này kiểm cả 4, cộng các chỗ tôi thấy dễ
sai khi tự viết resolver.

LƯU Ý VỀ TIỀN ĐỀ: tài liệu nói bảng phẳng gây "nhân đôi regulator". Tôi đã đo
trước khi viết code — KHÔNG xảy ra (1/8/20 xy-lanh đều ra 1 dòng FRL, luật
R-FRL-01 có scope per_system). Nên test "chỉ 1 dòng FRL" dưới đây xác nhận đồ thị
KHÔNG làm hỏng hành vi vốn đã đúng, chứ không phải nó sửa được lỗi gì.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tmpdb                                # noqa: E402,F401  PHẢI trước crawler.db
from crawler import db                      # noqa: E402
from engine import classify as CL           # noqa: E402
from engine import graph as G               # noqa: E402
from engine import materialize              # noqa: E402
from engine import tree as T                # noqa: E402

import web.server as W                      # noqa: E402

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}   {detail}")


def cad_graph(n_pairs=8, with_plc=True, with_manual=True):
    """Sơ đồ giống hình CAD tham khảo: n cụm van+xy-lanh, chung 1 FRL."""
    nodes = [{"id": "frl", "group": "frl", "code": "AC30B-03DG-A",
              "label": "Filter Regulator", "qty": 1,
              "ports": [{"id": "IN", "kind": "pneumatic"},
                        {"id": "OUT", "kind": "pneumatic"}]}]
    edges = []
    if with_plc:
        nodes.append({"id": "plc", "group": "plc", "label": "PLC",
                      "attrs": {"voltage": "24VDC"},
                      "ports": [{"id": "out", "kind": "electrical"}]})
    for i in range(n_pairs):
        v, c = f"v{i}", f"c{i}"
        nodes.append({"id": v, "group": "valve", "label": f"SV{i + 1}",
                      "overrides": {"valve_function": "double" if i % 2 else "single"},
                      "ports": [{"id": "1", "kind": "pneumatic"},
                                {"id": "2", "kind": "pneumatic"},
                                {"id": "12", "kind": "electrical"}]})
        nodes.append({"id": c, "group": "cylinder", "code": "CDM2L32-500Z",
                      "label": f"CYL{i + 1}", "qty": 1,
                      "ports": [{"id": "A", "kind": "pneumatic"},
                                {"id": "B", "kind": "pneumatic"}]})
        edges += [
            {"id": f"e{i}a", "from": v, "from_port": "2", "to": c, "to_port": "A",
             "kind": "pneumatic_control"},
            {"id": f"e{i}b", "from": "frl", "from_port": "OUT", "to": v,
             "to_port": "1", "kind": "pneumatic_supply"},
        ]
        if with_plc:
            edges.append({"id": f"e{i}c", "from": "plc", "from_port": "out",
                          "to": v, "to_port": "12", "kind": "electrical_signal"})
    if with_manual:
        nodes.append({"id": "x1", "group": "custom", "code": "XYZ-NONSTD-01",
                      "label": "Cảm biến tự chế", "manual": True, "qty": 2,
                      "note": "mua ngoài"})
    return {"nodes": nodes, "edges": edges}


CFG = {"tube_total_m": 80, "tube_roll_length_m": 20, "valve_series_size": "SY5000",
       "main_line_port_size": "3/8", "frl_size": "30"}


# ── MỤC 8: test case chấp nhận ───────────────────────────────────────────────
def test_muc8_chap_nhan():
    con = db.connect()
    r = W.api_bom(con, {"graph": cad_graph(), "config": dict(CFG), "name": "cad"})
    con.close()
    check("dựng được BOM từ đồ thị", not r.get("error"), r.get("error", ""))
    if r.get("error"):
        return

    # (1) chỉ 1 dòng Filter Regulator, không nhân theo số cylinder
    frl = [l for l in r["lines"] if l["layer"] == "air_prep"]
    check("chỉ 1 dòng bộ xử lý khí (không nhân theo 8 xy-lanh)",
          len(frl) == 1, f"{len(frl)} dòng: {[l['part_number'] for l in frl]}")

    # (2) 8 cụm chung 1 nguồn → engine thấy đúng 1 vùng khí
    check("nhận ra 8 cụm dùng chung 1 vùng khí",
          r["graph_info"]["supply_zones"] == 1,
          f"thấy {r['graph_info']['supply_zones']} vùng")

    # (3) điện áp coil lấy từ node PLC, có ghi lại nguồn gốc
    check("điện áp coil lấy từ node PLC (24VDC)",
          r["graph_info"].get("voltage_from_plc") == "24VDC",
          str(r["graph_info"].get("voltage_from_plc")))
    check("điện áp 24VDC vào đúng cấu hình dự án",
          str(r["project"].get("voltage")) == "24VDC",
          str(r["project"].get("voltage")))

    # (4) node tự do vào BOM, KHÔNG sinh cảnh báo "chưa hiểu mã"
    man = [l for l in r["lines"] if l.get("source") == "manual"]
    check("node tự do xuất hiện trong BOM", len(man) == 1,
          f"{len(man)} dòng")
    check("node tự do giữ đúng số lượng người dùng khai",
          man and man[0]["qty"] == 2, str(man))
    check("node tự do vào layer 'other' (group custom)",
          man and man[0]["layer"] == "other", str(man))
    blob = json.dumps(r["warnings"], ensure_ascii=False)
    check("KHÔNG cảnh báo 'chưa hiểu mã' cho node tự do",
          "XYZ-NONSTD-01" not in blob, blob[:120])
    check("dòng node tự do KHÔNG có rule_code (phân biệt với dòng engine suy)",
          man and man[0].get("rule_code") is None, str(man))


# ── các chỗ tôi thấy dễ sai khi tự viết resolver ─────────────────────────────
def test_hai_vung_khi_thi_bao_thieu():
    """2 vùng khí → engine chỉ sinh 1 FRL, PHẢI báo thiếu thay vì im lặng."""
    g = cad_graph(n_pairs=4, with_plc=False, with_manual=False)
    g["nodes"].append({"id": "frl2", "group": "frl", "code": "AC30B-03DG-A",
                       "label": "FRL vùng 2", "qty": 1,
                       "ports": [{"id": "OUT", "kind": "pneumatic"}]})
    g["nodes"].append({"id": "v9", "group": "valve", "label": "SV9",
                       "ports": [{"id": "1", "kind": "pneumatic"}]})
    g["edges"].append({"id": "z1", "from": "frl2", "from_port": "OUT",
                       "to": "v9", "to_port": "1", "kind": "pneumatic_supply"})
    con = db.connect()
    r = W.api_bom(con, {"graph": g, "config": dict(CFG), "name": "2zone"})
    con.close()
    check("nhận ra 2 vùng khí", r["graph_info"]["supply_zones"] == 2,
          str(r["graph_info"]["supply_zones"]))
    codes = [w["code"] for w in r["warnings"]]
    check("báo rõ engine chỉ sinh 1 bộ xử lý khí cho 2 vùng",
          "MULTI_SUPPLY_ZONE" in codes, str(codes))


def test_noi_sai_loai_cong_thi_canh_bao():
    """Nối cổng điện vào cổng khí → cảnh báo, KHÔNG chặn cứng."""
    g = {"nodes": [
        {"id": "p", "group": "plc", "label": "PLC",
         "ports": [{"id": "out", "kind": "electrical"}]},
        {"id": "c", "group": "cylinder", "code": "CDM2L32-500Z", "qty": 1,
         "ports": [{"id": "A", "kind": "pneumatic"}]}],
        "edges": [{"id": "e", "from": "p", "from_port": "out", "to": "c",
                   "to_port": "A", "kind": "electrical_signal"}]}
    con = db.connect()
    r = W.api_bom(con, {"graph": g, "config": dict(CFG), "name": "bad-port"})
    con.close()
    codes = [w["code"] for w in r["warnings"]]
    check("cảnh báo nối sai loại cổng", "PORT_KIND_MISMATCH" in codes, str(codes))
    check("KHÔNG chặn cứng — vẫn dựng được BOM", not r.get("error"),
          str(r.get("error")))


def test_loai_van_khai_o_van_truyen_xuong_xylanh():
    """Người vẽ khai loại van Ở NODE VAN; bảng phẳng bắt khai ở dòng xy-lanh.

    Đây là lợi ích cụ thể của đồ thị: biết van nào điều khiển xy-lanh nào nên
    truyền được thuộc tính theo cạnh pneumatic_control.
    """
    g = {"nodes": [
        {"id": "v", "group": "valve", "label": "SV1",
         "overrides": {"valve_function": "3pos_exhaust"},
         "ports": [{"id": "2", "kind": "pneumatic"}]},
        {"id": "c", "group": "cylinder", "code": "CDM2L32-500Z", "qty": 1,
         "ports": [{"id": "A", "kind": "pneumatic"}]}],
        "edges": [{"id": "e", "from": "v", "from_port": "2", "to": "c",
                   "to_port": "A", "kind": "pneumatic_control"}]}
    con = db.connect()
    res = G.resolve(con, g)
    con.close()
    check("van↔xy-lanh map được từ cạnh pneumatic_control",
          res["info"]["controlled"].get("c") == ["v"],
          str(res["info"]["controlled"]))
    over = res["inputs"][0][2] if res["inputs"] else {}
    check("loại van khai ở node VAN truyền xuống xy-lanh",
          over.get("valve_function") == "3pos_exhaust", str(over))


def test_cong_that_tach_A_B():
    """qty:2 trong interfaces.yaml phải tách thành 2 cổng A/B có id riêng.

    Không tách thì đồ thị vô nghĩa — không biết van nối cửa A hay cửa B.
    """
    con = db.connect()
    t = materialize.load_templates()
    ps = G.ports_for(con, "CDM2L32-500Z", "cylinder", t)
    con.close()
    ids = [p["id"] for p in ps]
    check("cửa khí tách thành A và B", "A" in ids and "B" in ids, str(ids))
    air = [p for p in ps if p["id"] in ("A", "B")]
    check("cổng A/B mang cỡ ren thật đọc từ catalog",
          all(p.get("size") == "1/8" and p.get("standard") == "Rc" for p in air),
          str(air))
    # rod_end cũng là `thread` nhưng là mối nối CƠ KHÍ, không phải đường khí.
    rod = next((p for p in ps if p["id"] == "rod_end"), None)
    check("ren đầu cần xếp là cơ khí, không phải khí",
          rod and rod["kind"] == "mechanical", str(rod))


def test_payload_phang_van_chay():
    """Giữ tương thích ngược: payload phẳng cũ không được vỡ."""
    con = db.connect()
    r = W.api_bom(con, {"inputs": [{"code": "CDM2L32-500Z", "qty": 3,
                                    "overrides": {"valve_function": "double"}}],
                        "config": dict(CFG), "name": "flat"})
    con.close()
    check("payload phẳng vẫn dựng được BOM", not r.get("error"), str(r.get("error")))
    check("payload phẳng KHÔNG có graph_info", "graph_info" not in r)


def test_luu_va_doc_lai_do_thi():
    """Đồ thị phải sống sót cùng project, không chỉ dùng một lần rồi bỏ."""
    con = db.connect()
    g = cad_graph(n_pairs=2, with_plc=False, with_manual=False)
    r = W.api_bom(con, {"graph": g, "config": dict(CFG), "name": "persist"})
    back = G.load(con, r["project_id"])
    con.close()
    check("đọc lại được đồ thị đã lưu", back is not None)
    check("số node khớp", back and len(back["nodes"]) == len(g["nodes"]),
          f"{len(back['nodes']) if back else '?'} vs {len(g['nodes'])}")
    check("số cạnh khớp", back and len(back["edges"]) == len(g["edges"]))


def test_do_thi_chi_co_node_tu_do():
    """Sơ đồ chỉ có thiết bị ngoài catalog vẫn phải ra BOM, không lỗi."""
    g = {"nodes": [{"id": "m", "group": "sensor", "code": "ABC-1", "label": "cảm biến",
                    "manual": True, "qty": 5}], "edges": []}
    con = db.connect()
    r = W.api_bom(con, {"graph": g, "config": dict(CFG), "name": "manual-only"})
    con.close()
    check("sơ đồ toàn node tự do vẫn ra BOM", not r.get("error"), str(r.get("error")))
    check("dòng tự do vào layer electrical (group sensor)",
          r["lines"] and r["lines"][0]["layer"] == "electrical", str(r["lines"]))


def test_do_thi_rong_bao_loi_ro_rang():
    con = db.connect()
    r = W.api_bom(con, {"graph": {"nodes": [], "edges": []}, "config": dict(CFG)})
    con.close()
    check("sơ đồ rỗng báo lỗi bằng tiếng Việt dễ hiểu",
          bool(r.get("error")) and "sơ đồ" in r["error"].lower(), str(r.get("error")))


def test_api_groups():
    g = W.api_groups()
    keys = {x["key"] for x in g["groups"]}
    check("palette có nhóm xy-lanh/van/xử lý khí/PLC/tuỳ chỉnh",
          {"cylinder", "valve", "frl", "plc", "custom"} <= keys, str(sorted(keys)))
    layers = {x["layer"] for x in g["groups"]}
    known = {"actuator", "valve", "air_prep", "piping", "accessory",
             "electrical", "other"}
    check("mọi nhóm map vào layer đã có trong index.html",
          layers <= known, str(layers - known))
    check("có 4 loại cạnh như tài liệu yêu cầu", len(g["edge_kinds"]) == 4)
    check("có suy đoán loại cạnh mặc định theo cặp nhóm",
          len(g["default_edge_kind"]) >= 8)
    # van phải có cổng điện — interfaces.yaml không có cổng điện nào
    vp = next(x for x in g["groups"] if x["key"] == "valve")["ports"]
    check("van có cổng điện (coil) — interfaces.yaml không cấp dữ liệu này",
          any(p["kind"] == "electrical" for p in vp), str(vp))


# ── Ba lỗi tìm ra khi người dùng dùng thật (2026-08-24) ─────────────────────

def _station(i, code):
    return {"id": f"v{i}", "type": "valve", "name": f"SV{i}", "code": "", "qty": 1,
            "attrs": {}, "children": [
                {"id": f"c{i}", "type": "cylinder", "name": "Xy-lanh", "code": code,
                 "qty": 1, "attrs": {}, "children": []}]}


def _tree(codes):
    return {"id": "frl", "type": "frl", "name": "FRL", "code": "", "qty": 1,
            "attrs": {}, "children": [_station(i + 1, c) for i, c in enumerate(codes)]}


def test_them_tram_thi_van_cu_phai_tinh_lai():
    """Thêm trạm → cỡ van của TRẠM CŨ phải tính lại theo lưu lượng mới.

    LỖI THẬT: fill_codes() bỏ qua node "đã có mã" nên trạm 1 giữ SY3220 (SY3000,
    đủ cho 1 xy-lanh) trong khi trạm 2,3,4 nhận SY5220 → van trạm 1 THIẾU CỠ và
    cả máy lẫn hai cỡ van trên cùng manifold.
    """
    con = db.connect()
    tree = _tree([])
    sizes = []
    for i in range(1, 5):
        tree["children"].append(_station(i, "CDM2L32-500Z"))
        r = W.api_bom(con, {"tree": tree, "config": dict(CFG), "name": f"b{i}"})
        tree = r["tree"]
        sizes = [n.get("code") for n, _, _ in T.walk(tree) if n["type"] == "valve"]
    con.close()
    check("4 trạm cùng xy-lanh → CÙNG một cỡ van", len(set(sizes)) == 1, str(sizes))
    check("cỡ van cuối là SY5000 (lưu lượng 4 xy-lanh)",
          all("SY5" in (c or "") for c in sizes), str(sizes))


def test_ma_ban_go_khong_bi_ghi_de():
    """Mã người dùng gõ phải sống sót qua mọi lần dựng lại.

    `filled_by_bom` lưu CHÍNH GIÁ TRỊ engine điền, không phải cờ true/false — nhờ
    vậy so được "còn khớp ⇒ tính lại" với "đã khác ⇒ người dùng đè ⇒ giữ".
    """
    con = db.connect()
    tree = _tree(["CDM2L32-500Z"] * 3)
    r = W.api_bom(con, {"tree": tree, "config": dict(CFG), "name": "a"})
    tree = r["tree"]
    T.find(tree, "v1")["code"] = "SY7220-5DZE-C6"      # cố ý KHÔNG xoá dấu cũ
    r = W.api_bom(con, {"tree": tree, "config": dict(CFG), "name": "b"})
    tree = r["tree"]
    v1 = T.find(tree, "v1")
    check("mã bạn gõ được giữ", v1.get("code") == "SY7220-5DZE-C6", str(v1.get("code")))
    tree["children"].append(_station(9, "CDM2L32-500Z"))
    r = W.api_bom(con, {"tree": tree, "config": dict(CFG), "name": "c"})
    con.close()
    v1 = T.find(r["tree"], "v1")
    check("thêm trạm nữa vẫn giữ mã bạn gõ",
          v1.get("code") == "SY7220-5DZE-C6", str(v1.get("code")))


def test_phu_kien_treo_dung_cha_va_dung_so_luong():
    """Phụ kiện engine sinh phải treo đúng node mẹ, số lượng THEO TỪNG xy-lanh.

    LỖI THẬT: dòng BOM gộp theo mã nên khi chia về từng xy-lanh tôi chia ĐỀU —
    2 con CDM2 + 1 con MGPM dùng chung mã tiết lưu (tổng 6) ra 3/3 thay vì 4/2.
    Sửa bằng cách for_items mang {mã: số lượng} thay vì chỉ danh sách mã.
    """
    con = db.connect()
    tree = {"id": "frl", "type": "frl", "name": "FRL", "code": "", "qty": 1,
            "attrs": {}, "children": [
                {"id": "v1", "type": "valve", "name": "SV1", "code": "", "qty": 1,
                 "attrs": {}, "children": [
                     {"id": "c1", "type": "cylinder", "name": "A",
                      "code": "CDM2L32-500Z", "qty": 2, "attrs": {}, "children": []}]},
                {"id": "v2", "type": "valve", "name": "SV2", "code": "", "qty": 1,
                 "attrs": {}, "children": [
                     {"id": "c2", "type": "cylinder", "name": "B",
                      "code": "MGPM25-200Z-M9BL", "qty": 1, "attrs": {},
                      "children": []}]}]}
    r = W.api_bom(con, {"tree": tree, "config": dict(CFG), "name": "phukien"})
    con.close()
    c1 = T.find(r["tree"], "c1")
    c2 = T.find(r["tree"], "c2")
    sc1 = [c for c in c1["children"] if c["type"] == "speed_controller"]
    sc2 = [c for c in c2["children"] if c["type"] == "speed_controller"]
    check("tiết lưu treo dưới xy-lanh, không ngang hàng", sc1 and sc2,
          f"{len(sc1)}/{len(sc2)}")
    check("2 xy-lanh CDM2 → 4 tiết lưu (không phải chia đều)",
          sc1 and sc1[0]["qty"] == 4, str(sc1))
    check("1 xy-lanh MGPM → 2 tiết lưu", sc2 and sc2[0]["qty"] == 2, str(sc2))
    sens = [c for c in c1["children"] if c["type"] == "sensor"]
    check("cảm biến cũng treo dưới xy-lanh", len(sens) == 1, str(sens))


def test_dung_lai_khong_cong_don_phu_kien():
    """Bấm Dựng BOM nhiều lần: phụ kiện KHÔNG được nhân lên."""
    con = db.connect()
    tree = _tree(["CDM2L32-500Z"])
    n = []
    for i in range(3):
        r = W.api_bom(con, {"tree": tree, "config": dict(CFG), "name": f"r{i}"})
        tree = r["tree"]
        n.append(sum(1 for x, _, _ in T.walk(tree) if x.get("from_bom")))
    con.close()
    check("dựng 3 lần, số phụ kiện không đổi", len(set(n)) == 1, str(n))


def test_khoa_engine_tu_tinh_khong_con_bat_khai():
    """Cỡ van và loại van engine đã tính → không được nằm trong 'cần bạn khai'."""
    keys = {k for k, _, _ in W.NEEDS_INPUT}
    comp = {k for k, _, _ in W.ENGINE_COMPUTED}
    check("valve_series_size chuyển sang nhóm engine tự tính",
          "valve_series_size" in comp and "valve_series_size" not in keys)
    check("valve_function chuyển sang nhóm engine tự tính",
          "valve_function" in comp and "valve_function" not in keys)
    check("frl_size chuyển sang nhóm engine tự tính — đã số hoá đồ thị AC",
          "frl_size" in comp and "frl_size" not in keys)
    check("áp nguồn xưởng VẪN hỏi — catalog không có thông số này",
          "supply_pressure_mpa" in keys)
    check("điểm nối đầu nối VẪN hỏi — số lượng không suy được từ đồ thị",
          "fitting_points" in keys and "fitting_points" not in comp)
    check("cỡ cửa đường trục chuyển sang engine tự tính — đọc từ đồ thị",
          "main_line_port_size" in comp and "main_line_port_size" not in keys)


def test_moi_vat_tu_deu_co_node_tren_so_do():
    """Vật tư engine sinh ra PHẢI có node trên sơ đồ, kể cả khi chưa có mã.

    Yêu cầu của bạn: "chưa có mã do thiếu dữ liệu đầu vào nhưng phần mềm vẫn phải
    liệt kê ra ở CẢ sơ đồ và BOM".

    ĐO ĐƯỢC TRƯỚC KHI SỬA: nhập 1 mã xy-lanh, không khai cấu hình → BOM 8 dòng mà
    cây chỉ 5 node. Thiếu: floating joint (CÓ mã, JA40-14-150), đầu nối, ống, bộ AC.
    Nguyên nhân: tree.py suy loại node từ `layer` bằng bảng ba dòng, nên bốn thứ
    này không có dòng nào để suy.
    """
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ"])
    r = W.api_bom(con, {"tree": tree, "config": {}, "name": "liet-ke"})
    con.close()
    types = [n["type"] for n, _, _ in T.walk(r["tree"])]
    for t in ("joint", "fitting", "tubing"):
        check(f"sơ đồ có node {t}", t in types, str(types))
    gapn = {n["type"]: n for n, _, _ in T.walk(r["tree"]) if n.get("gap_fields")}
    check("node đầu nối đánh dấu chưa có mã", "fitting" in gapn, str(list(gapn)))
    check("node ống đánh dấu chưa có mã", "tubing" in gapn, str(list(gapn)))
    check("node FRL (gốc) đánh dấu chưa có mã", "frl" in gapn, str(list(gapn)))
    frl = gapn.get("frl") or {}
    check("dấu đó NÓI RA còn thiếu trường nào",
          "supply_pressure_mpa" in (frl.get("gap_fields") or []),
          str(frl.get("gap_fields")))
    jo = [n for n, _, _ in T.walk(r["tree"]) if n["type"] == "joint"]
    check("floating joint treo dưới XY-LANH (vặn vào ren đầu cần)",
          jo and T.parent_of(r["tree"], jo[0]["id"])["type"] == "cylinder", str(jo))
    check("joint có mã thật, không phải node rỗng",
          jo and (jo[0].get("code") or "").startswith("JA"), str(jo))


def test_node_manifold_khong_duoc_nhan_ma_VAN():
    """Node manifold KHÔNG được nhận mã van.

    LỖI THẬT, ĐO ĐƯỢC: fill_codes() gom dòng theo `layer`, mà layer 'valve' chứa
    cả van, manifold, gasket, end plate. Nhánh "tầng này chỉ có một dòng thì gán"
    điền SY5220-5MZE-C6 (mã VAN) vào node MANIFOLD. Sơ đồ hiện MÃ SAI — nặng hơn
    hiện thiếu. Sửa bằng cách ghép theo `node_type` do luật khai.
    """
    con = db.connect()
    tree = {"id": "frl", "type": "frl", "name": "FRL", "code": "", "qty": 1,
            "attrs": {}, "children": [
                {"id": "m1", "type": "manifold", "name": "Đế", "code": "", "qty": 1,
                 "attrs": {}, "children": [_station(1, "CDM2B40-150AZ")]}]}
    r = W.api_bom(con, {"tree": tree, "config": {}, "name": "mfd"})
    con.close()
    m1 = T.find(r["tree"], "m1")
    v1 = T.find(r["tree"], "v1")
    check("van vẫn được điền mã van", (v1.get("code") or "").startswith("SY"),
          str(v1.get("code")))
    check("manifold KHÔNG bị điền mã van",
          not (m1.get("code") or "").startswith("SY"), str(m1.get("code")))
    check("manifold chưa có mã thì NÓI RA", bool(m1.get("gap_fields")), str(m1))


def test_van_dieu_khien_xylanh_chua_go_ma_thi_khong_doan():
    """Van điều khiển xy-lanh CHƯA GÕ MÃ thì không được điền mã van của xy-lanh khác.

    Cỡ van suy từ lưu lượng của chính xy-lanh nó điều khiển. Xy-lanh chưa biết thì
    cỡ van chưa biết — điền vào là đoán im lặng. Đo được: nhánh "loại này chỉ có
    một dòng" gán mã van của trạm 1 cho trạm 2.
    """
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ"])
    tree["children"].append(_station(2, ""))
    r = W.api_bom(con, {"tree": tree, "config": {}, "name": "doan"})
    con.close()
    v2 = T.find(r["tree"], "v2")
    check("van của xy-lanh chưa gõ mã: để trống, không đoán",
          not v2.get("code"), str(v2.get("code")))
    items = [l.get("item") or "" for l in r["lines"] if l.get("status") == "gap"]
    check("nhưng van đó VẪN có dòng trong BOM",
          any("Van" in i for i in items), str(items))
    check("xy-lanh chưa gõ mã cũng có dòng trong BOM",
          any("Xy-lanh" in i for i in items), str(items))


def test_node_tren_so_do_khong_bi_bien_mat_khoi_BOM():
    """Node có trên sơ đồ mà chưa có mã PHẢI vào BOM — chiều ngược của fill_codes.

    ĐO ĐƯỢC: resolve() có `if not code: continue`, nên node 'Giảm âm' người dùng
    tạo mà chưa gõ mã thì KHÔNG có trong BOM, trong khi sơ đồ vẫn vẽ nó. Bảng và
    sơ đồ nói hai chuyện khác nhau, và bảng là cái đem đi mua hàng.
    """
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ"])
    tree["children"][0]["children"].append(
        {"id": "sil1", "type": "silencer", "name": "Giảm âm xả", "code": "",
         "qty": 2, "attrs": {}, "children": []})
    r = W.api_bom(con, {"tree": tree, "config": dict(CFG), "name": "silen"})
    con.close()
    sil = [l for l in r["lines"] if "Giảm âm" in (l.get("item") or "")]
    check("giảm âm chưa có mã vẫn có dòng BOM", len(sil) == 1,
          str([l.get("item") for l in r["lines"]]))
    check("dòng đó mang SỐ LƯỢNG người dùng khai", sil and sil[0]["qty"] == 2,
          str(sil))
    check("và nói rõ còn thiếu 'mã hàng'", sil and sil[0]["gap_fields"] == ["code"],
          str(sil))


def test_khai_du_du_lieu_thi_dau_chua_co_ma_phai_MAT():
    """Khai đủ dữ liệu → dấu 'chưa có mã' phải biến mất, không dính lại.

    Dấu đặt trên node CỦA NGƯỜI DÙNG (node gốc FRL), không phải node engine sinh,
    nên drop_generated() phải xoá riêng — chỉ xoá con `from_bom` là dấu còn nguyên
    và sơ đồ báo thiếu mãi.
    """
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ"])
    r = W.api_bom(con, {"tree": tree, "config": {}, "name": "thieu"})
    tree = r["tree"]
    check("lúc thiếu: gốc FRL báo chưa có mã", bool(T.find(tree, "frl").get("gap_fields")))
    cfg = dict(CFG)
    cfg.update({"supply_pressure_mpa": 0.6, "fitting_points": [
        {"shape": "L", "tube_od": "06", "port_size": "1/4", "thread_material": "N",
         "port_standard": "R", "seal_method": "S", "qty": 4}]})
    r = W.api_bom(con, {"tree": tree, "config": cfg, "name": "du"})
    con.close()
    frl = T.find(r["tree"], "frl")
    check("khai đủ: gốc FRL có mã AC", (frl.get("code") or "").startswith("AC"),
          str(frl.get("code")))
    check("và dấu chưa-có-mã đã mất", not frl.get("gap_fields"),
          str(frl.get("gap_fields")))
    fit = [n for n, _, _ in T.walk(r["tree"]) if n["type"] == "fitting"]
    check("đầu nối giờ là node CÓ MÃ", fit and (fit[0].get("code") or "").startswith("KQ2"),
          str(fit))


def test_cong_phan_loai_theo_ma():
    """CỔNG: series nào gõ mã vào được thì phải phân loại được.

    Không có cổng này thì thêm một tệp ngữ pháp mới là người dùng gõ mã hợp lệ mà
    phần mềm nói "không biết đây là gì" — im lặng tụt hậu.
    """
    con = db.connect()
    ok, rep = CL.gate(con)
    con.close()
    for name, good, detail in rep:
        check(f"{name} — {detail[:70]}", good, detail)
    check("cổng phân loại ĐẠT", ok)


def test_go_ma_thi_tu_phan_loai():
    """Gõ mã → biết loại thiết bị. Yêu cầu (2) của bạn.

    ĐO TRƯỚC KHI LÀM: phân loại theo `category.layer` của crawl thì 48 mã BOM có
    layer mà chỉ 5 mã suy ra được DUY NHẤT một loại — layer gộp van/đế/gasket vào
    một chỗ, và AS (tiết lưu) còn bị crawl xếp 'electrical'. Nên bảng khai tay
    19 dòng, kèm cổng ở test trên.
    """
    con = db.connect()
    want = {
        "CDM2B40-150AZ": "cylinder", "SY5220-5MZE-C6": "valve",
        "SS5Y5-20-04": "manifold", "AS2201F-02-06SA": "speed_controller",
        "KQ2L06-02NS": "fitting", "TU0604BU-20": "tubing",
        "D-M9BW": "sensor", "JA40-14-150": "joint", "JB20-5-080-X11": "joint",
        "AN15-02": "silencer", "AC30-03DG-A": "frl",
    }
    for code, nt in want.items():
        r = CL.classify(con, code)
        check(f"{code} → {nt}", r.get("ok") and r["node_type"] == nt,
              str(r.get("node_type") or r.get("reason")))
    # VAI TRÒ THẮNG SERIES: gasket parse ra họ SY-5-E (van) nhưng nó là phụ kiện đế.
    for code in ("SY5000-GS-1", "SY5000-26-20A"):
        r = CL.classify(con, code)
        check(f"{code} là phụ kiện đế, KHÔNG phải van",
              r.get("ok") and r["node_type"] == "manifold_part",
              str(r.get("node_type") or r.get("reason")))
    # Mã đọc được nhưng chưa khai loại, và mã sai: phải NÓI KHÔNG BIẾT, không đoán.
    for code in ("ISE20-N-M-C6L-B", "XYZ123", ""):
        r = CL.classify(con, code)
        check(f"{code or '(rỗng)'} → nói không biết, kèm cách đi tiếp",
              not r.get("ok") and r.get("reason") and r.get("how"), str(r))
    con.close()


def test_phan_loai_noi_ro_gan_duoc_vao_dau():
    """Phân loại xong phải nói gắn được vào đâu — không bắt người dùng tự dò."""
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ"])
    r = W.api_classify(con, "AN15-02", tree)
    labels = [p["label"] for p in r.get("placements") or []]
    check("giảm âm gắn được lên van (BOM thật AN15-02 ×2 cho 11 van)",
          any("SV" in l for l in labels), str(labels))
    check("giảm âm KHÔNG gắn vào xy-lanh", not any("lanh" in l for l in labels),
          str(labels))
    r = W.api_classify(con, "SY5000-GS-1", tree)
    check("cây chưa có manifold → gasket không có chỗ nào, và nói ra",
          r["ok"] and not r["placements"], str(r.get("placements")))
    check("nhưng vẫn cho biết nó cần cha loại gì",
          r["allowed_parents"] == ["manifold"], str(r.get("allowed_parents")))
    con.close()


def test_goi_y_ma_khong_lan_loai_khac():
    """Danh sách mã gợi ý phải theo LOẠI, không theo tiền tố mã.

    LỖI CŨ ĐO ĐƯỢC: api_codes lọc bằng tiền tố viết tay theo layer, nên chọn
    "Đế manifold" vẫn nhận mã VAN SY5220, và SY5000-GS-1 (gasket) hiện trong danh
    sách van vì khớp tiền tố 'SY'.
    """
    con = db.connect()
    mfd = W.api_codes(con, "manifold")["codes"]
    val = W.api_codes(con, "valve")["codes"]
    prt = W.api_codes(con, "manifold_part")["codes"]
    con.close()
    check("gợi ý cho đế manifold chỉ có mã SS5Y", mfd and all(c.startswith("SS5Y") for c in mfd),
          str(mfd[:4]))
    check("gợi ý cho van KHÔNG lẫn mã đế", not any(c.startswith("SS5Y") for c in val),
          str([c for c in val if c.startswith("SS5Y")][:3]))
    check("gợi ý cho van KHÔNG lẫn gasket/end plate",
          not any("-GS-" in c or "-26-" in c for c in val),
          str([c for c in val if "-GS-" in c or "-26-" in c][:3]))
    check("phụ kiện đế có danh sách riêng và không rỗng", len(prt) > 0, str(prt[:3]))


def test_quan_he_cha_con_khong_con_o_cut():
    """Thiết bị đầu nối/ống/tiết lưu phải nối tiếp được nhau.

    Bạn báo "quá ít lựa chọn". Đo được 8/14 loại node KHÔNG thêm được gì, trong đó
    có mối nối vật lý hiển nhiên: ống cắm vào cửa one-touch của tiết lưu và của
    đầu nối. Còn lại 5 loại là THIẾT BỊ ĐẦU CUỐI thật (cảm biến, giảm âm, khớp nối,
    phụ kiện đế, PLC) — không có gì vặn lên chúng, nên 0 là đúng.
    """
    kids = lambda t: [k for k, (a, _) in T.PARENT_OF.items() if t in a]
    check("ống cắm được vào tiết lưu (AS…F có one-touch sẵn)",
          "tubing" in kids("speed_controller"), str(kids("speed_controller")))
    check("ống cắm được vào đầu nối", "tubing" in kids("fitting"), str(kids("fitting")))
    check("đầu nối nối tiếp được đoạn ống", "fitting" in kids("tubing"),
          str(kids("tubing")))
    check("thiết bị ngoài catalog nhận được phụ kiện", len(kids("custom")) >= 5,
          str(kids("custom")))
    leaves = [t for t in G.GROUPS if not kids(t)]
    check("đúng 5 loại đầu cuối, và là những loại KHÔNG có gì vặn lên",
          set(leaves) == {"sensor", "silencer", "joint", "manifold_part", "plc"},
          str(sorted(leaves)))


def test_thiet_bi_tu_them_phai_vao_BOM_va_CSV():
    """Thiết bị bạn tự thêm (có mã) phải vào BOM, CSV và DB — không chỉ vẽ trên cây.

    ĐO ĐƯỢC TRƯỚC KHI SỬA: thêm node giảm âm 'AN15-02' ×2 → BOM KHÔNG hề nhắc tới
    nó. resolve() chỉ biến node actuator thành `inputs` và node 'Mã tự do' thành
    `manual_lines`; mọi node khác CÓ MÃ rơi vào khoảng trống. Bảng BOM vẽ được nó
    vì bảng vẽ theo cây, nhưng `lines` không có nên CSV và project_output đều thiếu
    — tức đơn mua hàng thiếu thiết bị.

    Phân loại theo mã (yêu cầu 2) làm lỗ này nặng hơn nhiều: giờ thêm thiết bị bất
    kỳ là chuyện một dòng gõ.
    """
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ"])
    tree["children"][0]["children"].append(
        {"id": "s1", "type": "silencer", "name": "AN15-02", "code": "AN15-02",
         "qty": 2, "attrs": {}, "children": []})
    r = W.api_bom(con, {"tree": tree, "config": dict(CFG), "name": "tuthem"})
    an = [l for l in r["lines"] if "AN15" in str(l.get("part_number"))]
    check("thiết bị tự thêm có dòng BOM", len(an) == 1, str(len(an)))
    check("đúng số lượng bạn khai", an and an[0]["qty"] == 2, str(an))
    check("KHÔNG dán nhãn 'không qua kiểm tra kỹ thuật' — mã này parse được",
          an and "kiểm tra kỹ thuật" not in an[0]["rationale"], str(an))
    csv = W.api_csv(con, r["project_id"])
    check("CSV xuất ra cũng có nó", "AN15-02" in csv, csv[:120])
    # dựng lại nhiều lần: không được nhân đôi
    t2 = r["tree"]
    for i in range(2):
        r = W.api_bom(con, {"tree": t2, "config": dict(CFG), "name": f"lai{i}"})
        t2 = r["tree"]
    an = [l for l in r["lines"] if "AN15" in str(l.get("part_number"))]
    check("dựng lại 3 lần vẫn đúng 1 dòng", len(an) == 1, str(len(an)))
    con.close()


def test_ma_sai_van_vao_BOM_kem_canh_bao():
    """Mã không đọc được: vẫn liệt kê, kèm cảnh báo. Bỏ đi là để đơn hàng thiếu."""
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ"])
    tree["children"][0]["children"].append(
        {"id": "s1", "type": "silencer", "name": "?", "code": "AN15-KHONG-CO-THAT",
         "qty": 1, "attrs": {}, "children": []})
    r = W.api_bom(con, {"tree": tree, "config": dict(CFG), "name": "masai"})
    con.close()
    check("mã sai vẫn có dòng BOM",
          any("KHONG-CO-THAT" in str(l.get("part_number")) for l in r["lines"]))
    w = [x for x in r["warnings"] if x.get("code") == "NODE_CODE_UNPARSED"]
    check("và có cảnh báo engine không kiểm được nó", len(w) == 1, str(len(w)))
    check("cảnh báo nói cách đi tiếp", w and w[0].get("fix"), str(w[:1]))


def test_lien_ket_cheo_van_tram_khac_dieu_khien():
    """Van trạm này điều khiển xy-lanh trạm khác — cây một-cha KHÔNG nói được.

    ĐO ĐƯỢC khi làm yêu cầu (4): đặt XL3 ở gốc rồi khai liên kết "SV3 điều khiển
    XL3" thì normalize() vẫn dịch XL3 về van ĐẦU TIÊN (SV1), vì nó chỉ lấy "node
    hợp lệ đầu tiên gặp được". Kết quả: bản đồ van↔xy-lanh nói XL3 do CẢ SV1 và SV3
    điều khiển — hai câu trái nhau, và cỡ van SV1 bị cộng thêm lưu lượng của một
    xy-lanh không thuộc nó. Nên liên kết bạn khai phải THẮNG phép đoán.
    """
    con = db.connect()
    tree = {"id": "frl", "type": "frl", "name": "FRL", "code": "", "attrs": {},
            "children": [_station(1, "CDM2B40-150AZ"), _station(2, "CDM2B32-100AZ"),
                         {"id": "v3", "type": "valve", "name": "SV3", "code": "",
                          "attrs": {}, "children": []},
                         {"id": "c3", "type": "cylinder", "name": "XL3 xa trạm",
                          "code": "CDM2B25-50AZ", "qty": 1, "attrs": {},
                          "children": []}]}
    links = [{"id": "L1", "from": "v3", "to": "c3", "kind": "pneumatic_control"}]
    r = W.api_bom(con, {"tree": tree, "links": links, "config": dict(CFG),
                        "name": "lienket"})
    con.close()
    ctrl = r["graph_info"]["controlled"]
    check("XL3 do ĐÚNG SV3 điều khiển, không phải SV1", ctrl.get("c3") == ["v3"],
          str(ctrl))
    check("mỗi xy-lanh khác vẫn đúng van của nó",
          ctrl.get("c1") == ["v1"] and ctrl.get("c2") == ["v2"], str(ctrl))
    check("XL3 được dịch về con của SV3 theo liên kết",
          (T.parent_of(r["tree"], "c3") or {}).get("id") == "v3")
    check("và NÓI RA là dịch theo liên kết bạn khai",
          any("theo liên kết" in (w.get("message") or "") for w in r["warnings"]),
          str([w.get("message") for w in r["warnings"]])[:200])
    check("SV3 nhận được mã van (trước đây để trống vì không biết nó kéo gì)",
          (T.find(r["tree"], "v3").get("code") or "").startswith("SY"),
          str(T.find(r["tree"], "v3").get("code")))


def test_lien_ket_duoc_luu_va_doc_lai():
    """Liên kết lưu CÙNG cây. Lưu riêng thì mở project cũ ra cây mới + liên kết cũ."""
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ", "CDM2B32-100AZ"])
    links = [{"id": "L1", "from": "v1", "to": "c2", "kind": "pneumatic_control"}]
    r = W.api_bom(con, {"tree": tree, "links": links, "config": dict(CFG), "name": "luu"})
    got = T.load_links(con, r["project_id"])
    check("đọc lại đúng liên kết đã lưu", len(got) == 1 and got[0]["from"] == "v1",
          str(got))
    # project lưu TRƯỚC khi có tính năng này: không có khoá 'links', không phải lỗi
    T.save(con, r["project_id"], r["tree"])
    check("project không có liên kết trả về [] chứ không vỡ",
          T.load_links(con, r["project_id"]) == [])
    con.close()


def test_xoa_thiet_bi_thi_lien_ket_treo_phai_bi_bo_va_BAO():
    """Xoá node → liên kết trỏ vào hư không. Bỏ IM LẶNG là người dùng tưởng còn nối."""
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ", "CDM2B32-100AZ"])
    links = [{"id": "L1", "from": "v1", "to": "c2", "kind": "pneumatic_control"},
             {"id": "L2", "from": "v1", "to": "khong-ton-tai",
              "kind": "pneumatic_control"}]
    r = W.api_bom(con, {"tree": tree, "links": links, "config": dict(CFG), "name": "treo"})
    con.close()
    check("liên kết treo bị bỏ", len(r["links"]) == 1, str(r["links"]))
    check("và có báo, không im lặng",
          any(w.get("code") == "LINKS_PRUNED" for w in r["warnings"]),
          str([w.get("code") for w in r["warnings"]]))


def test_lien_ket_sai_mien_tin_hieu_thi_bao():
    """Nối tín hiệu ĐIỆN vào ống khí phải báo — kiểm bằng chính dữ liệu cổng."""
    con = db.connect()
    tree = _tree(["CDM2B40-150AZ"])
    tree["children"][0]["children"].append(
        {"id": "tu1", "type": "tubing", "name": "Ống", "code": "", "attrs": {},
         "children": []})
    bad = [{"id": "L1", "from": "tu1", "to": "c1", "kind": "electrical_signal"},
           {"id": "L2", "from": "v1", "to": "v1", "kind": "pneumatic_supply"},
           {"id": "L3", "from": "v1", "to": "c1", "kind": "khong-co-loai-nay"}]
    r = W.api_bom(con, {"tree": tree, "links": bad, "config": dict(CFG), "name": "sai"})
    con.close()
    ws = [w for w in r["warnings"] if w.get("rule_code") == "T-LINK-01"]
    check("ống khí không có cổng điện → báo",
          any("cổng electrical" in (w.get("what") or "") for w in ws),
          str([w.get("what") for w in ws]))
    check("nối vào chính nó → báo",
          any("chính nó" in (w.get("what") or "") for w in ws),
          str([w.get("what") for w in ws]))
    check("loại liên kết không có thật → báo",
          any("không có thật" in (w.get("what") or "") for w in ws),
          str([w.get("what") for w in ws]))


def test_lien_ket_trung_canh_cha_con_khong_dem_hai_lan():
    """Liên kết trùng đúng quan hệ cha–con thì bỏ, không sinh cạnh thứ hai."""
    tree = _tree(["CDM2B40-150AZ"])
    g1 = T.to_graph(tree)
    g2 = T.to_graph(tree, [{"from": "v1", "to": "c1", "kind": "pneumatic_control"}])
    check("cạnh không tăng lên", len(g1["edges"]) == len(g2["edges"]),
          f'{len(g1["edges"])} → {len(g2["edges"])}')
    g3 = T.to_graph(tree, [{"from": "v1", "to": "c1", "kind": "electrical_signal"}])
    check("nhưng LOẠI khác thì vẫn là cạnh mới",
          len(g3["edges"]) == len(g1["edges"]) + 1, str(len(g3["edges"])))


def test_chuyen_cho_thiet_bi():
    """Chuyển thiết bị sang cha khác — và ba điều phải chặn."""
    def t():
        return {"id": "frl", "type": "frl", "name": "FRL", "children": [
            {"id": "v1", "type": "valve", "name": "SV1", "children": [
                {"id": "c1", "type": "cylinder", "name": "XL1", "children": [
                    {"id": "sc1", "type": "speed_controller", "name": "TL",
                     "children": []}]}]},
            {"id": "v2", "type": "valve", "name": "SV2", "children": []}]}
    tr = t()
    ok, pb = T.move(tr, "c1", "v2")
    check("chuyển xy-lanh sang van khác được", ok and not pb, str(pb))
    check("và nó thật sự nằm ở chỗ mới",
          (T.parent_of(tr, "c1") or {}).get("id") == "v2")
    check("cả nhánh con đi theo", T.find(tr, "sc1") is not None)
    ok, pb = T.move(t(), "c1", "frl")
    check("KHÔNG chuyển vào cha sai loại", not ok and "không lắp vào" in pb["what"],
          str(pb))
    check("và nói ra chỗ nào nhận được", "valve" in (pb or {}).get("fix", ""), str(pb))
    ok, pb = T.move(t(), "frl", "v1")
    check("KHÔNG chuyển được gốc", not ok, str(pb))
    # con cháu + loại hợp lệ: đế manifold nhận cha 'regulator', đặt regulator làm
    # con của đế rồi chuyển đế vào chính nó
    cyc = {"id": "frl", "type": "frl", "name": "FRL", "children": [
        {"id": "m1", "type": "manifold", "name": "Đế", "children": [
            {"id": "rg", "type": "regulator", "name": "Điều áp", "children": []}]}]}
    ok, pb = T.move(cyc, "m1", "rg")
    check("KHÔNG chuyển vào con cháu của chính nó (mất cả nhánh)",
          not ok and "con cháu" in pb["what"], str(pb))
    check("cây không bị hỏng sau lần chuyển bị chặn",
          len([n for n, _, _ in T.walk(cyc)]) == 3)


def test_route_api_move_co_that():
    """Route /api/move phải được đăng ký — môi trường chặn bind nên kiểm mã nguồn."""
    import inspect
    src = inspect.getsource(W.Handler.do_POST)
    check('có route /api/move', '"/api/move"' in src)
    check("gọi đúng hàm", "api_move(" in src)


def test_lien_ket_dien_tu_PLC_doi_ma_van():
    """Liên kết tín hiệu điện từ PLC phải ĐỔI ĐƯỢC mã van — không chỉ vẽ cho đẹp.

    HAI LỖI ĐO ĐƯỢC khi làm yêu cầu (4):
      1. PARENT_OF khai plc = ((None,),) tức PLC chỉ được làm GỐC, mà gốc luôn là
         nguồn khí → KHÔNG BAO GIỜ thêm được node PLC từ giao diện cây. Vì thế
         bước 4 của graph.resolve() (suy điện áp coil từ PLC) chưa từng dùng được.
      2. Không có liên kết thì điện áp khai ở node PLC bị bỏ qua hoàn toàn.
    Test này khoá bằng chứng CỤ THỂ: cùng một cây, chỉ thêm liên kết mà chữ số điện
    áp trong mã van đổi 5 (24VDC) → 6 (12VDC).
    """
    con = db.connect()

    def mk(v):
        return {"id": "frl", "type": "frl", "name": "FRL", "code": "", "attrs": {},
                "children": [_station(1, "CDM2B40-150AZ"),
                             {"id": "plc1", "type": "plc", "name": "PLC", "code": "",
                              "attrs": {}, "overrides": {"voltage": v},
                              "children": []}]}
    out = {}
    for v in ("24VDC", "12VDC"):
        for tag, links in (("khong", []),
                           ("co", [{"from": "plc1", "to": "v1",
                                    "kind": "electrical_signal"}])):
            r = W.api_bom(con, {"tree": mk(v), "links": links,
                                "config": {"valve_series_size": "SY5000"},
                                "name": "plc"})
            out[(v, tag)] = (next((n.get("code") for n, _, _ in T.walk(r["tree"])
                                   if n["type"] == "valve"), None),
                             r["graph_info"].get("voltage_from_plc"),
                             T.find(r["tree"], "plc1") is not None)
    con.close()
    check("PLC đặt được vào cây (trước đây chỉ được làm gốc nên không thêm được)",
          all(v[2] for v in out.values()), str(out))
    check("không liên kết → điện áp PLC bị bỏ qua",
          out[("12VDC", "khong")][1] is None, str(out[("12VDC", "khong")]))
    check("có liên kết → engine suy được điện áp",
          out[("12VDC", "co")][1] == "12VDC", str(out[("12VDC", "co")]))
    check("và MÃ VAN đổi theo: 5 (24VDC) → 6 (12VDC)",
          out[("24VDC", "co")][0] == "SY5220-5MZE-C6"
          and out[("12VDC", "co")][0] == "SY5220-6MZE-C6",
          f'{out[("24VDC", "co")][0]} vs {out[("12VDC", "co")][0]}')


def test_hai_vung_khi_KHONG_khai_duoc_bang_cay():
    """Khoá GIỚI HẠN đã đo, để không ai tưởng liên kết làm được việc này.

    Cây có ĐÚNG MỘT gốc và mọi node đều có đường lên gốc, nên supply_zones() luôn
    ra 1 vùng. Liên kết chỉ THÊM được kết nối, không cắt được cái sẵn có. Đã thử ba
    cách; test này giữ hai cách tiêu biểu. Máy hai nhánh khí độc lập hiện chỉ khai
    được qua payload {graph} — test_hai_vung_khi_thi_bao_thieu ở trên chứng minh
    đường đó vẫn chạy.
    """
    con = db.connect()
    base = {"id": "frl", "type": "frl", "name": "FRL", "code": "", "attrs": {},
            "children": [_station(1, "CDM2B40-150AZ"),
                         {"id": "src2", "type": "custom", "name": "Khí nhánh 2",
                          "code": "", "attrs": {}, "children": []},
                         _station(2, "CDM2B32-100AZ")]}
    for tag, links in (("nguồn 2 khai bằng node custom, không nối", []),
                       ("nối nguồn 2 tới van trạm 2 bằng liên kết cấp khí",
                        [{"from": "src2", "to": "v2", "kind": "pneumatic_supply"}])):
        r = W.api_bom(con, {"tree": json.loads(json.dumps(base)), "links": links,
                            "config": dict(CFG), "name": "zone"})
        check(f"vẫn 1 vùng khí — {tag}", r["graph_info"]["supply_zones"] == 1,
              str(r["graph_info"]["supply_zones"]))
    con.close()


if __name__ == "__main__":
    print("Kiểm đồ thị đấu nối")
    print("=" * 60)
    for fn in (test_muc8_chap_nhan, test_hai_vung_khi_thi_bao_thieu,
               test_noi_sai_loai_cong_thi_canh_bao,
               test_loai_van_khai_o_van_truyen_xuong_xylanh,
               test_cong_that_tach_A_B, test_payload_phang_van_chay,
               test_luu_va_doc_lai_do_thi, test_do_thi_chi_co_node_tu_do,
               test_do_thi_rong_bao_loi_ro_rang, test_api_groups,
               test_them_tram_thi_van_cu_phai_tinh_lai,
               test_ma_ban_go_khong_bi_ghi_de,
               test_phu_kien_treo_dung_cha_va_dung_so_luong,
               test_dung_lai_khong_cong_don_phu_kien,
               test_khoa_engine_tu_tinh_khong_con_bat_khai,
               test_moi_vat_tu_deu_co_node_tren_so_do,
               test_node_manifold_khong_duoc_nhan_ma_VAN,
               test_van_dieu_khien_xylanh_chua_go_ma_thi_khong_doan,
               test_node_tren_so_do_khong_bi_bien_mat_khoi_BOM,
               test_khai_du_du_lieu_thi_dau_chua_co_ma_phai_MAT,
               test_cong_phan_loai_theo_ma,
               test_go_ma_thi_tu_phan_loai,
               test_phan_loai_noi_ro_gan_duoc_vao_dau,
               test_goi_y_ma_khong_lan_loai_khac,
               test_quan_he_cha_con_khong_con_o_cut,
               test_thiet_bi_tu_them_phai_vao_BOM_va_CSV,
               test_ma_sai_van_vao_BOM_kem_canh_bao,
               test_lien_ket_cheo_van_tram_khac_dieu_khien,
               test_lien_ket_duoc_luu_va_doc_lai,
               test_xoa_thiet_bi_thi_lien_ket_treo_phai_bi_bo_va_BAO,
               test_lien_ket_sai_mien_tin_hieu_thi_bao,
               test_lien_ket_trung_canh_cha_con_khong_dem_hai_lan,
               test_chuyen_cho_thiet_bi,
               test_route_api_move_co_that,
               test_lien_ket_dien_tu_PLC_doi_ma_van,
               test_hai_vung_khi_KHONG_khai_duoc_bang_cay):
        print(f"\n{fn.__name__}")
        fn()
    print("\n" + "=" * 60)
    print(f"{ok} đạt · {fail} lỗi")
    sys.exit(1 if fail else 0)
