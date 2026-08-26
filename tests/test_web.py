"""Test tầng API của web UI — gọi hàm trực tiếp, không cần mở socket.

    python3 tests/test_web.py

Vì sao không test qua HTTP: sandbox của môi trường này chặn bind() socket
(PermissionError: Operation not permitted), nên không chạy được server ở đây.
Các hàm api_* thuần tuý (con, payload) → dict nên test được trực tiếp, và đó cũng
là chỗ chứa logic; phần http.server chỉ là lớp vận chuyển.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tmpdb                                # noqa: E402,F401  PHẢI trước crawler.db
from crawler import db      # noqa: E402
from web import server as W  # noqa: E402


def test_series_list():
    con = db.connect()
    rows = W.api_series(con)
    assert len(rows) >= 10, f"phải có ≥10 series có ngữ pháp, có {len(rows)}"
    codes = {r["catalog_id"] for r in rows}
    for want in ("CM2-CDM2-Z-E", "AS1-E", "KQ2-E", "MGP-Z-E", "CQS-Z-E", "SY-5-E"):
        assert want in codes, f"thiếu {want}"
    assert all(r["part_prefix"] for r in rows), "series nào cũng phải có part_prefix"
    con.close()


def test_parse_ok_va_loi():
    con = db.connect()
    good = W.api_parse(con, "CDM2L32-500Z")
    assert good["ok"] is True
    assert good["attrs"]["bore_mm"] == 32.0
    slots = {t["slot"]: t["code"] for t in good["trace"]}
    assert slots["mounting"] == "L" and slots["stroke"] == "500"

    bad = W.api_parse(con, "CDM2X99-500Z")
    assert bad["ok"] is False and bad["unparsed"], "mã sai phải chỉ ra phần chưa hiểu"

    empty = W.api_parse(con, "")
    assert empty["ok"] is False and empty["error"]
    con.close()


def test_bom_day_du():
    con = db.connect()
    r = W.api_bom(con, {
        "inputs": [{"code": "CDM2L32-500Z", "qty": 5,
                    "overrides": {"valve_function": "double"}}],
        "config": {"tube_total_m": 60, "main_line_port_size": "3/8",
                   "frl_size": "40", "valve_series_size": "SY5000",
                   "use_manifold": "true", "manifold_type": "20, 23, 20SA, 23SA"},
    })
    assert "error" not in r, r.get("error")
    pns = {l["part_number"]: l["qty"] for l in r["lines"]}
    assert pns.get("CDM2L32-500Z") == 5
    assert pns.get("AS2201F-01-06SA") == 10
    assert pns.get("SY5220-5MZE-C6") == 5, f"van: {pns}"
    assert pns.get("SY5000-GS-1") == 5, "có manifold → phải có gasket"
    assert r["project_id"] > 0
    # mọi dòng không phải actuator phải có lý do
    for l in r["lines"]:
        if l["layer"] != "actuator":
            assert l.get("rule_code") and l.get("rationale")
    con.close()


def test_bom_thieu_khai_thi_bao_gap():
    """Không khai gì → engine báo gap cho thứ nó KHÔNG suy được.

    ĐÃ ĐỔI theo mục 6 của spec: `valve_function` và `valve_series_size` giờ engine
    TỰ QUYẾT (theo tác động và theo lưu lượng) nên KHÔNG còn nằm trong gap. Còn
    tube_total_m (phụ thuộc layout) và main_line_port_size (phụ thuộc đồ thị FRL
    chưa số hoá) thì vẫn phải hỏi.
    """
    con = db.connect()
    r = W.api_bom(con, {"inputs": [{"code": "CDM2L32-500Z", "qty": 5}], "config": {}})
    rules = {g.get("rule_code") for g in r["gaps"]}
    for want in ("R-TUBE-01", "R-FRL-01"):
        assert want in rules, f"{want} phải báo gap khi chưa khai. gaps={rules}"
    assert "R-VLV-01" not in rules, \
        f"loại van giờ engine tự quyết, không được hỏi nữa. gaps={rules}"
    assert any(l["layer"] == "valve" for l in r["lines"]), \
        "engine tự quyết được thì phải sinh van, không để trống"
    # mọi gap phải đủ 3 phần để UI hiển thị được
    for g in r["gaps"]:
        assert g.get("what"), g
        assert g.get("field") or g.get("fix"), g
    con.close()

def test_bom_khong_co_input():
    con = db.connect()
    r = W.api_bom(con, {"inputs": [], "config": {}})
    assert "error" in r
    con.close()


def test_csv_xuat_duoc():
    con = db.connect()
    r = W.api_bom(con, {
        "inputs": [{"code": "CDM2L32-500Z", "qty": 2,
                    "overrides": {"valve_function": "single"}}],
        "config": {"tube_total_m": 20, "valve_series_size": "SY5000"}})
    csv_txt = W.api_csv(con, r["project_id"])
    lines = [l for l in csv_txt.strip().split("\n") if l]
    assert lines[0].startswith("Tầng,Mã hàng"), lines[0]
    assert len(lines) > 2, "CSV phải có dòng dữ liệu"
    assert "CDM2L32-500Z" in csv_txt
    con.close()


def test_valve_function_theo_tung_xylanh():
    """Hai xy-lanh cùng loại, khác chức năng → hai mã van khác nhau."""
    con = db.connect()
    r = W.api_bom(con, {
        "inputs": [
            {"code": "CDM2L32-500Z", "qty": 3, "overrides": {"valve_function": "single"}},
            {"code": "CDM2B40-150AZ", "qty": 2,
             "overrides": {"valve_function": "3pos_exhaust"}},
        ],
        "config": {"tube_total_m": 40, "valve_series_size": "SY5000"}})
    valves = {l["part_number"]: l["qty"] for l in r["lines"] if l["layer"] == "valve"}
    assert "SY5120-5MZE-C6" in valves, f"single → SY5120. có {valves}"
    assert "SY5420-5MZE-C6" in valves, f"3pos_exhaust → SY5420. có {valves}"
    con.close()


def test_duong_dan_api_classify_co_that():
    """Route /api/classify phải được đăng ký trong do_POST.

    Môi trường này CHẶN BIND nên không dựng được server thật (tests/test_docker.py
    ghi cùng điều đó ở dòng 257), mà mọi test khác gọi hàm api_* trực tiếp — nên
    hàm chạy đúng vẫn không chứng minh UI gọi được. Kiểm ngay trên mã nguồn của
    do_POST: thiếu dòng route là UI bấm '+ Thêm theo mã' nhận 404.
    """
    import inspect
    src = inspect.getsource(W.Handler.do_POST)
    assert '"/api/classify"' in src, src
    assert "api_classify(" in src, src


def test_classify_tra_ve_du_thu_UI_can():
    """Hợp đồng với UI: đủ node_type + label + allowed_parents + placements."""
    con = db.connect()
    tree = {"id": "frl", "type": "frl", "name": "FRL", "children": [
        {"id": "v1", "type": "valve", "name": "SV1", "children": []}]}
    r = W.api_classify(con, "AN15-02", tree)
    con.close()
    for k in ("ok", "node_type", "label", "layer", "allowed_parents",
              "placements", "why"):
        assert k in r, f"thiếu khoá {k}: {r}"
    assert r["node_type"] == "silencer", r
    assert [p["id"] for p in r["placements"]] == ["v1"], r["placements"]


if __name__ == "__main__":
    ok = fail = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✓ {name}")
                ok += 1
            except AssertionError as e:
                print(f"  ✗ {name}: {e}")
                fail += 1
    print(f"\n{ok} pass, {fail} fail")
    sys.exit(1 if fail else 0)
