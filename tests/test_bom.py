"""Test engine BOM. Chạy: python3 tests/test_bom.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import db                      # noqa: E402
from engine import bom, materialize         # noqa: E402


def _build(inputs, project=None):
    con = db.connect()
    bom.seed_rules(con)
    res = bom.build(con, inputs, project, project_name="test")
    con.close()
    return res


def _line(res, pn):
    return next((l for l in res["lines"] if l["part_number"] == pn), None)


def test_bom_5_xylanh():
    """5× CDM2L32-500Z → BOM 4 tầng, số lượng đúng."""
    r = _build([("CDM2L32-500Z", 5)])
    assert _line(r, "CDM2L32-500Z")["qty"] == 5
    # 2 speed controller mỗi xy-lanh × 5
    sc = _line(r, "AS2201F-01-06S")
    assert sc and sc["qty"] == 10, f"speed controller: {sc}"
    # 2 cảm biến mỗi xy-lanh × 5
    sw = _line(r, "D-M9BW")
    assert sw and sw["qty"] == 10, f"switch: {sw}"
    # 1 van mỗi xy-lanh
    vl = next((l for l in r["lines"] if l["layer"] == "valve"), None)
    assert vl and vl["qty"] == 5, f"van: {vl}"
    # ống: suy từ 10 đầu one-touch × 3 m / cuộn 20 m = 2 cuộn
    tu = _line(r, "TU0604BU-20")
    assert tu and tu["qty"] == 2, f"ống: {tu}"


def test_moi_dong_co_giai_thich():
    """Mọi dòng không phải input đều phải có rule_code + rationale."""
    r = _build([("CDM2L32-500Z", 5)])
    for l in r["lines"]:
        if l["layer"] == "actuator":
            continue
        assert l.get("rule_code"), f"{l['part_number']} không có rule_code"
        assert l.get("rationale") and len(l["rationale"]) > 20, \
            f"{l['part_number']} thiếu lý do"


def test_khong_canh_bao_ren_gia():
    """R male vào Rc female là ĐÚNG — không được báo MIXED_THREAD_STANDARD.

    Lỗi thật đã gặp: luật cũ đếm số chuẩn ren khác nhau nên BOM đúng (có Rc + R + M)
    luôn bị báo lỗi. Cảnh báo giả làm mất tin cậy toàn bộ output.
    """
    r = _build([("CDM2L32-500Z", 5)])
    codes = [w.get("code") for w in r["warnings"]]
    assert "MIXED_THREAD_STANDARD" not in codes, f"cảnh báo giả: {r['warnings']}"


def test_co_ren_that_khong_tuong_thich_thi_phai_bao():
    """Ngược lại: cặp ren thật sự không lắp được thì phải đếm ra."""
    con = db.connect()
    # dựng cặp giả: R 1/8 male (thật, của AS) vs NPT 1/8 female
    male = {"kind": "thread", "gender": "male", "standard": "R", "size": "1/8",
            "role": "air_in", "tube_od_mm": None}
    female = {"kind": "thread", "gender": "female", "standard": "NPT", "size": "1/8",
              "role": "air_port", "tube_od_mm": None}
    ok, why = materialize.mates(con, male, female)
    assert ok is False, f"R male vào NPT female phải KHÔNG lắp được: {why}"
    ok2, _ = materialize.mates(con, male, {**female, "standard": "Rc"})
    assert ok2 is True, "R male vào Rc female phải lắp được"
    con.close()


def test_bore_40_ra_ren_1_4():
    """Cỡ ren phải tra theo bore, không giả định một cỡ.

    PDF CM2 trang 14 cột P: bore 20/25/32 → 1/8, bore 40 → 1/4.
    """
    r = _build([("CDM2B40-150AZ", 2)])
    sc = next((l for l in r["lines"] if l["layer"] == "accessory"), None)
    assert sc and sc["part_number"] == "AS2201F-02-06S", \
        f"bore 40 phải ra speed controller ren 1/4: {sc}"


def test_gap_duoc_bao_khong_doan_bua():
    """FRL và manifold chưa có dữ liệu → phải vào gap, không được đoán mã."""
    r = _build([("CDM2L32-500Z", 5)])
    rules = {g.get("rule_code") for g in r["gaps"]}
    assert "R-FRL-01" in rules, "FRL phải báo gap (AC-A-E chưa có ngữ pháp)"
    assert "R-MFD-01" in rules, "manifold phải báo gap (mã SS5Y chưa giải mã)"
    for g in r["gaps"]:
        assert g.get("reason") and g.get("rationale"), f"gap thiếu lý do: {g}"


def test_ma_khong_parse_duoc_thi_bao():
    r = _build([("CDM2X99-500Z", 1)])
    assert any("CDM2X99" in (g.get("item") or "") for g in r["gaps"]), \
        f"mã sai phải vào gap: {r['gaps']}"


def test_tinh_toan():
    """Lực và lưu lượng — ø32 @ 0.5 MPa."""
    r = _build([("CDM2L32-500Z", 5)])
    c = r["calc"][0]
    assert 395 < c["thrust_push_N"] < 410, c["thrust_push_N"]   # π/4·32²·0.5 ≈ 402 N
    assert c["rod_mm"] == 12.0                                  # PDF trang 14
    assert c["piston_speed_mm_s"] == 667                        # 500mm / 0.75s
    assert r["system"]["required_flow_lpm"] > r["system"]["total_flow_lpm"]


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
