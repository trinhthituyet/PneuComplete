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
    check("cỡ cửa đường trục chuyển sang engine tự tính — đọc từ đồ thị",
          "main_line_port_size" in comp and "main_line_port_size" not in keys)


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
               test_khoa_engine_tu_tinh_khong_con_bat_khai):
        print(f"\n{fn.__name__}")
        fn()
    print("\n" + "=" * 60)
    print(f"{ok} đạt · {fail} lỗi")
    sys.exit(1 if fail else 0)
