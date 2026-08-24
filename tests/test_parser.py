"""Test hồi quy cho chuỗi crawl → PDF → ngữ pháp → parse mã hàng.

    python3 -m pytest tests/ -q          (nếu có pytest)
    python3 tests/test_parser.py         (chạy trực tiếp, không cần pytest)

Test cần DB đã có ngữ pháp CM2. Dựng lại bằng:
    python3 -m crawler.run init && crawl && pdf && python3 -m crawler.run grammar
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import db          # noqa: E402
from engine import parser       # noqa: E402

# Mã thật, trả lời đúng câu hỏi ban đầu của dự án
CASES = [
    ("CDM2L32-500Z", {
        "ok": True, "prefix": "CDM2",
        "slots": {"mounting": "L", "bore": "32", "stroke": 500,
                  "cushion": "Nil", "series_suffix": "Z"},
        "attrs": {"bore_mm": 32.0, "stroke_mm": 500,
                  "has_magnet": True, "cushion": "rubber_bumper"},
    }),
    ("CM2B40-150AZ", {
        "ok": True, "prefix": "CM2",
        "slots": {"mounting": "B", "bore": "40", "stroke": 150, "cushion": "A"},
        "attrs": {"bore_mm": 40.0, "stroke_mm": 150, "cushion": "air"},
    }),
    ("CDM2B32-100AZ-M9BW", {
        "ok": True, "prefix": "CDM2",
        "slots": {"auto_switch": "M9BW"},
        "attrs": {"auto_switch": "M9BW", "has_magnet": True},
    }),
]


def test_parse_cases():
    con = db.connect()
    for pn, want in CASES:
        got = parser.parse(con, pn)
        assert got.get("ok") == want["ok"], f"{pn}: ok={got.get('ok')} dư={got.get('unparsed')}"
        assert got["prefix"] == want["prefix"], f"{pn}: prefix {got['prefix']}"
        for k, v in want["slots"].items():
            assert got["slots"].get(k) == v, f"{pn}: slot {k}={got['slots'].get(k)!r} ≠ {v!r}"
        for k, v in want["attrs"].items():
            assert got["attrs"].get(k) == v, f"{pn}: attr {k}={got['attrs'].get(k)!r} ≠ {v!r}"
    con.close()


def test_as_speed_controller():
    """AS2201F-01-06S — chính mã đã tư vấn cho CDM2L32-500Z ở đầu dự án.
    Ngữ pháp nhập tay từ PDF 7-9-3-p0830-0838-AS-F trang 8."""
    con = db.connect()
    r = parser.parse(con, "AS2201F-01-06S")
    assert r["ok"], f"unparsed={r.get('unparsed')} missing={r.get('missing')}"
    assert r["attrs"]["port_standard"] == "R"
    assert r["attrs"]["port_size"] == "1/8"
    assert r["attrs"]["tube_od_mm"] == 6.0
    assert r["attrs"]["control"] == "meter_out"
    assert r["attrs"]["shape"] == "elbow"
    assert r["attrs"]["sealant"] is True
    # meter-in phải ra khác
    assert parser.parse(con, "AS2211F-01-06S")["attrs"]["control"] == "meter_in"
    # không có S ở cuối = không sealant
    assert parser.parse(con, "AS2201F-01-06")["attrs"]["sealant"] is False
    con.close()


def test_tubing():
    con = db.connect()
    r = parser.parse(con, "TU0604BU-20")
    assert r["ok"]
    assert r["attrs"]["tube_od_mm"] == 6.0 and r["attrs"]["tube_id_mm"] == 4.0
    assert r["attrs"]["roll_length_m"] == 20
    # thiếu ô bắt buộc thì phải báo, không được coi là hợp lệ
    bad = parser.parse(con, "TU0604BU")
    assert bad["ok"] is False and "roll_length" in (bad["missing"] or [])
    con.close()


def test_mounting_L_is_axial_foot():
    """Kiểm tra nhãn, không chỉ mã — đây là điều người dùng thực sự đọc."""
    con = db.connect()
    r = parser.parse(con, "CDM2L32-500Z")
    label = next(t[2] for t in r["trace"] if t[0] == "mounting")
    assert label and "axial foot" in label.lower(), f"nhãn mounting = {label!r}"
    con.close()


def test_khong_doan_bua():
    """Mã sai phải báo không hiểu, KHÔNG được tự suy diễn."""
    con = db.connect()
    r = parser.parse(con, "CDM2X99-500Z")   # 'X99' không phải mounting hợp lệ
    assert r["ok"] is False
    assert r["unparsed"], "phải chỉ ra phần chưa hiểu"
    con.close()


def test_grammar_cm2_day_du():
    con = db.connect()
    sid = con.execute(
        "select id from series where catalog_id='CM2-CDM2-Z-E'").fetchone()["id"]
    slots = {r["name"]: r["n"] for r in con.execute(
        """select cs.name, count(co.id) n from code_slot cs
           left join code_option co on co.slot_id=cs.id
           where cs.series_id=? group by cs.id""", (sid,))}
    assert slots.get("mounting") == 13, f"mounting phải có 13 option, có {slots.get('mounting')}"
    assert slots.get("bore") == 4
    assert "stroke" in slots and "cushion" in slots
    con.close()


def test_bang_tra_doc_duoc_ma_engine_tu_sinh():
    """Mã nằm trong BẢNG TRA (gasket, end plate) phải đọc ngược được.

    LỖI THẬT: engine SINH được SY5000-26-20A và SY5000-GS-1 (bảng tra đọc tay từ
    PDF trang 45/73) nhưng KHÔNG ĐỌC NGƯỢC được chính mã mình sinh ra — parser chỉ
    đi qua ngữ pháp, mà các mã đó gắn vào series SY-5-E có ngữ pháp VAN
    (SY5220-5MZE-C6). Nó thử đọc như mã van rồi báo dư "0-26-20A".
    """
    con = db.connect()
    for code, role in (("SY5000-GS-1", "gasket"),
                       ("SY5000-26-20A", "end_plate"),
                       ("SY5000-26-21A", "end_plate")):
        r = parser.parse(con, code)
        assert r.get("ok"), f"{code}: {r}"
        assert (r.get("attrs") or {}).get("role") == role, r
    con.close()


def test_bang_tra_khong_lan_at_ngu_phap():
    """Chỉ mã có `role` mới qua bảng tra — còn lại vẫn dùng ngữ pháp.

    Bảng `part` chứa CẢ mã do engine tự ghi lúc materialize. Nhận hết là parser
    đọc lại kết quả của chính mình thay vì đọc catalog: sai lệch nào của engine
    sẽ tự khẳng định là đúng.
    """
    con = db.connect()
    for code in ("CDM2L32-500Z", "SY5220-5MZE-C6", "AS2201F-01-06SA"):
        r = parser.parse(con, code)
        assert r.get("ok"), f"{code}: {r}"
        assert r.get("source") != "bảng tra trong catalog", \
            f"{code} phải parse bằng NGỮ PHÁP, không phải bảng tra: {r.get('source')}"
    con.close()


def test_hau_to_don_hang_NA():
    """Hậu tố '-NA' là của ĐƠN HÀNG, không phải ô mã — tách ra và GHI LẠI.

    Đo trên BOM thật: máy 24-236 có 5/6 mã SMC kết thúc '-NA', máy 23-432 thì
    0/6. Tìm khắp catalog SY plug-in không thấy bảng nào giải nghĩa '-NA'.
    Bỏ im lặng thì người dùng không biết engine đã lược cái gì.
    """
    con = db.connect()
    r = parser.parse(con, "SY50M-26-1A-NA")
    assert r.get("ok"), r
    assert r.get("order_suffix") == "NA", r
    assert (r.get("attrs") or {}).get("order_suffix") == "NA", r
    # mã không có hậu tố thì không được bịa ra
    r2 = parser.parse(con, "SY5000-26-20A")
    assert r2.get("order_suffix") is None, r2
    con.close()


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
