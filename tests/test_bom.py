"""Test engine BOM. Chạy: python3 tests/test_bom.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tmpdb                                # noqa: E402,F401  PHẢI trước crawler.db
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
    """5× CDM2L32-500Z → BOM 4 tầng, số lượng đúng.

    tube_total_m phải khai tường minh: engine không tự ước lượng chiều dài ống
    (mục A3-5 — người dùng bác bỏ giá trị mặc định 3 m/mối nối).
    """
    r = _build([("CDM2L32-500Z", 5)], {"tube_total_m": 60})
    assert _line(r, "CDM2L32-500Z")["qty"] == 5
    # 2 speed controller mỗi xy-lanh × 5. Mã kết thúc 'SA' = Push-lock type —
    # đúng loại BOM máy thật dùng (AS2201F-01-06SA), xác nhận 2026-08-18.
    sc = _line(r, "AS2201F-01-06SA")
    assert sc and sc["qty"] == 10, f"speed controller: {sc}"
    # 2 cảm biến mỗi xy-lanh × 5
    sw = _line(r, "D-M9BW")
    assert sw and sw["qty"] == 10, f"switch: {sw}"
    # 1 van mỗi xy-lanh (chưa khai cỡ van → không có dòng van, xem test riêng)
    # ống: 60 m khai vào / cuộn 20 m = 3 cuộn
    tu = _line(r, "TU0604BU-20")
    assert tu and tu["qty"] == 3, f"ống: {tu}"


def test_khong_khai_chieu_dai_ong_thi_bao_gap():
    """Chưa khai tube_total_m → phải báo gap, KHÔNG tự ước lượng (A3-5)."""
    r = _build([("CDM2L32-500Z", 5)])
    assert not _line(r, "TU0604BU-20"), "không được tự sinh dòng ống khi chưa biết chiều dài"
    g = next((g for g in r["gaps"] if g.get("rule_code") == "R-TUBE-01"), None)
    assert g and g["field"] == "tube_total_m", f"gaps: {r['gaps']}"


def test_duong_kinh_can_lay_tu_series_khong_hardcode():
    """rod_dia_mm phải đến từ attrs của mã (pdf_dim_table đọc bảng kích thước).

    Bản đầu hardcode trong calc.py và ghi sai bore 40 = 16 (bảng ghi 14) — mục A3-1.
    """
    from engine import parser as P
    con = db.connect()
    for pn, want in (("CDM2L32-500Z", 12.0), ("CDM2B40-150AZ", 14.0)):
        a = P.parse(con, pn)["attrs"]
        assert a.get("rod_dia_mm") == want, f"{pn}: rod={a.get('rod_dia_mm')} ≠ {want}"
        assert a.get("_source", "").startswith("bảng kích thước"), \
            f"{pn}: thiếu truy nguồn cho rod_dia_mm"
    con.close()


def test_moi_dong_co_giai_thich():
    """Mọi dòng không phải input đều phải có rule_code + rationale."""
    r = _build([("CDM2L32-500Z", 5)], {"tube_total_m": 60})
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
    assert sc and sc["part_number"] == "AS2201F-02-06SA", \
        f"bore 40 phải ra speed controller ren 1/4: {sc}"


FRL_CFG = {"tube_total_m": 60, "main_line_port_size": "3/8", "frl_size": "40",
           "valve_series_size": "SY5000"}


def test_speed_controller_dung_ho_push_lock():
    """Engine phải đề xuất họ Push-lock (hậu tố A) — loại BOM thật mua.

    Tôi từng tư vấn AS2201F-01-06S (thiếu A) vì đọc PDF AS-E-E (núm thường).
    BOM máy 23-432 và 24-236 đều dùng AS2201F-01-06SA / AS1201F-M5-06A.
    """
    from engine import parser as P
    r = _build([("CDM2L32-500Z", 5)], {"tube_total_m": 60})
    sc = next(l for l in r["lines"] if l["layer"] == "accessory")
    assert sc["part_number"].endswith("SA"), f"phải là push-lock: {sc['part_number']}"
    con = db.connect()
    a = P.parse(con, sc["part_number"])["attrs"]
    assert a.get("knob") == "push_lock"
    con.close()


def test_floating_joint_theo_ren_dau_can():
    """JA chọn theo ren đầu cần, tin cậy thấp vì 'không phải tất cả trường hợp'."""
    r = _build([("CDM2L32-500Z", 5)], {"tube_total_m": 60})
    ja = _line(r, "JA30-10-125")            # CM2 ø32 → ren M10x1.25
    assert ja and ja["qty"] == 5, f"floating joint: {ja}"
    assert ja["confidence"] <= 0.6, "phải là đề xuất tin cậy thấp, không khẳng định"


def test_mgp_ra_dung_ma_nhu_bom_that():
    """MGP là xy-lanh dùng nhiều nhất trong BOM thật (22 cái).

    Máy 24-236 sheet (B): MGPM16-125Z-M9BL ×4 đi cùng AS1201F-M5-06A ×8.
    Engine phải ra ĐÚNG cặp đó — ø16 dùng ren MÉT M5, không phải Rc.
    """
    r = _build([("MGPM25-200Z-M9BL", 4), ("MGPM16-125Z-M9BL", 4)],
               {"tube_total_m": 40, "main_line_port_size": "3/8", "frl_size": "30"})
    assert _line(r, "AS2201F-01-06SA")["qty"] == 8, "ø25 (Rc1/8) → speed ctrl 1/8"
    m5 = _line(r, "AS1201F-M5-06A")
    assert m5 and m5["qty"] == 8, f"ø16 (M5) → speed ctrl M5: {m5}"
    assert "ren mét" in (m5.get("note") or ""), m5.get("note")


def test_sealant_la_so_thich_khong_phai_rang_buoc():
    """Cỡ M5 không có loại sealant → engine nhượng bộ + ghi chú, KHÔNG báo gap."""
    r = _build([("MGPM16-125Z-M9BL", 4)],
               {"tube_total_m": 20, "main_line_port_size": "1/4", "frl_size": "20"})
    m5 = _line(r, "AS1201F-M5-06A")
    assert m5, "phải sinh được mã dù không có sealant"
    assert "sealant" in (m5.get("note") or ""), f"phải ghi chú nhượng bộ: {m5.get('note')}"


def test_joint_bo_qua_xylanh_co_dan_huong():
    """MGP có dẫn hướng sẵn → không đề xuất floating joint (suy diễn, chờ xác nhận)."""
    r = _build([("MGPM25-200Z-M9BL", 4)], {"tube_total_m": 20})
    assert not any(l["part_number"].startswith("JA") for l in r["lines"])
    # còn CM2 không dẫn hướng thì vẫn đề xuất
    r2 = _build([("CDM2L32-500Z", 2)], {"tube_total_m": 20})
    assert _line(r2, "JA30-10-125"), "CM2 vẫn phải có joint"


def test_frl_can_khai_co_cua():
    """Chưa khai main_line_port_size → gap, không tự chọn cỡ FRL."""
    r = _build([("CDM2L32-500Z", 5)], {"tube_total_m": 60})
    assert not any(l["layer"] == "air_prep" for l in r["lines"])
    g = next(g for g in r["gaps"] if g.get("rule_code") == "R-FRL-01")
    assert g["field"] == "main_line_port_size", g
    assert g.get("options"), "phải liệt kê cỡ cửa hợp lệ, không bắt tra catalog"


def test_frl_co_cua_mo_ho_thi_liet_ke_ung_vien():
    """Cửa 3/8 có ở AC25/30/40 → engine phải liệt kê, không chọn bừa."""
    r = _build([("CDM2L32-500Z", 5)], {"tube_total_m": 60, "main_line_port_size": "3/8"})
    g = next(g for g in r["gaps"] if g.get("rule_code") == "R-FRL-01")
    assert "size" in g["reason"], g["reason"]


def test_frl_chot_co_thi_ra_ma():
    """Khai đủ → ra mã AC, và PHẢI kèm cảnh báo chưa kiểm được lưu lượng."""
    r = _build([("CDM2L32-500Z", 5)], FRL_CFG)
    frl = next((l for l in r["lines"] if l["layer"] == "air_prep"), None)
    assert frl and frl["part_number"] == "AC40B-03DG-A", f"FRL: {frl}"
    codes = [w.get("code") for w in r["warnings"]]
    # FRL_CFG không khai áp nguồn → engine chưa tra được đồ thị nên vẫn cảnh báo
    assert "FRL_FLOW_UNVERIFIED" in codes, \
        "thiếu áp nguồn thì phải cảnh báo chưa kiểm được lưu lượng"


def test_kiem_duoc_luu_luong_thi_khong_con_canh_bao_cu():
    """Đồ thị đã số hoá — không được tiếp tục nói 'engine không kiểm được'."""
    r = _build([("CDM2L32-500Z", 5)], dict(FRL_AUTO, frl_series="AC-D-E"))
    codes = [w.get("code") for w in r["warnings"]]
    assert "FRL_FLOW_UNVERIFIED" not in codes, \
        f"đã tra được đồ thị thì không được nói chưa kiểm được: {codes}"


def test_co_ac_khai_thieu_thi_bao_thieu():
    """Người dùng chốt cỡ quá nhỏ → engine phải nói ra, không im lặng làm theo."""
    r = _build([("CDM2B40-150AZ", 8)], dict(FRL_AUTO, frl_series="AC-D-E",
                                            frl_size="20"))
    w = next((x for x in r["warnings"] if x.get("code") == "FRL_SIZE_TOO_SMALL"), None)
    assert w, f"phải cảnh báo cỡ AC khai quá nhỏ: {[x.get('code') for x in r['warnings']]}"
    assert "20" in w["message"] and w["severity"] == "warn", w


def test_frl_khong_lubricator_mac_dinh():
    """CM2 dùng mỡ sẵn → mặc định chọn loại B (Filter+Regulator), không có dầu."""
    from engine import parser as P
    con = db.connect()
    a = P.parse(con, "AC40B-03DG-A")["attrs"]
    assert a["has_lubricator"] is False and a["has_mist_separator"] is False
    assert a["port_size"] == "3/8" and a["port_standard"] == "Rc"
    con.close()


def test_van_sinh_dung_ma_nhu_bom_that():
    """Van sinh từ ngữ pháp phải ra ĐÚNG mã BOM máy 23-432 dùng.

    SY5220-5MZE-C6 = SY5000 · 2-pos double · body ported · 24VDC · M plug ·
    light+surge Z · manual override E · one-touch ø6.
    """
    r = _build([("CDM2L32-500Z", 5)],
               {"tube_total_m": 60, "valve_series_size": "SY5000",
                "valve_function": "double"})
    v = next(l for l in r["lines"] if l["layer"] == "valve")
    assert v["part_number"] == "SY5220-5MZE-C6", f"van: {v['part_number']}"
    assert v["qty"] == 5


def test_van_tu_de_xuat_khong_de_trong():
    """Mục 6 của spec ĐỔI hợp đồng: engine tự đề xuất loại van, không để trống.

    ⚠ ĐÁNH ĐỔI ĐÃ BIẾT — ghi lại để người sau không tưởng là miễn phí:
    golden test trên máy 23-432 cho thấy MỘT máy dùng đồng thời SY5120 (single) ×5,
    SY5220 (double) ×2, SY5420 (3-pos exhaust) ×4. Nghĩa là mặc định "mọi xy-lanh
    → 5/2 double" SAI với thực tế ở nhiều cơ cấu. Bản trước vì vậy để trống và đòi
    khai.

    Spec yêu cầu tự đề xuất + cho override, nên nay engine đề xuất `double` cho
    xy-lanh tác động kép. Bù lại BẮT BUỘC:
      · phát cảnh báo AUTO_VALVE_FUNCTION để người dùng biết mà kiểm lại
      · override ở từng node phải thắng
    """
    r = _build([("CDM2L32-500Z", 5)],
               {"tube_total_m": 60, "tube_roll_length_m": 20, "tube_color": "BU"})
    assert not any(g.get("field") == "valve_function" for g in r["gaps"]), \
        f"không còn để trống bắt khai: {r['gaps']}"
    assert any(l["layer"] == "valve" for l in r["lines"]), "phải sinh được van"
    w = next((w for w in r["warnings"] if w["code"] == "AUTO_VALVE_FUNCTION"), None)
    assert w, "tự quyết mà im lặng là che mất chỗ cần kiểm lại"
    assert "3pos" in (w.get("rationale") or ""), \
        "cảnh báo phải nói rõ có lựa chọn dừng giữa hành trình"

    # override ở từng cơ cấu vẫn thắng — đây là điều kiện để đánh đổi trên chấp nhận được
    r2 = _build([("CDM2L32-500Z", 5, {"valve_function": "3pos_exhaust"})],
                {"tube_total_m": 60, "tube_roll_length_m": 20, "tube_color": "BU",
                 "valve_series_size": "SY5000"})
    assert any("5420" in l["part_number"] for l in r2["lines"]), \
        f"override phải thắng: {[l['part_number'] for l in r2['lines']]}"

def test_van_base_mounted_khong_co_cua_rieng():
    """base_mounted → mã không có -C6 vì cửa nằm trên manifold."""
    from engine import parser as P
    con = db.connect()
    a = P.parse(con, "SY7140-5LZE-02")["attrs"]
    assert a["mounting"] == "base_mounted" and a["series_size"] == "SY7000"
    b = P.parse(con, "SY5120-5MZE-C6")["attrs"]
    assert b["mounting"] == "body_ported" and b["tube_od_mm"] == 6.0
    con.close()


# use_manifold là cờ RIÊNG, không suy từ valve_mounting: golden test cho thấy
# manifold dùng được với cả van body-ported (máy 23-432: SS5Y5-20-12 + SY5120-5MZE-C6).
MFD_CFG = {"tube_total_m": 60, "valve_series_size": "SY5000",
           "valve_function": "double", "use_manifold": True,
           "manifold_type": "20, 23, 20SA, 23SA"}


def test_gasket_va_endplate_dung_ma_bom():
    """Van cắm manifold → gasket mỗi van + 2 end plate, đúng mã BOM 23-432."""
    r = _build([("CDM2L32-500Z", 5)], MFD_CFG)
    g = _line(r, "SY5000-GS-1")
    assert g and g["qty"] == 5, f"gasket 1 cái/van: {g}"
    assert "trang 45" in (g.get("note") or ""), g.get("note")
    ep = _line(r, "SY5000-26-20A")
    assert ep and ep["qty"] == 2, f"2 end plate: {ep}"


def test_endplate_can_khai_kieu_manifold():
    """Type 20 → SY5000-26-20A, Type 20P → SY5000-26-21A. Chưa khai → gap."""
    r = _build([("CDM2L32-500Z", 5)],
               {**MFD_CFG, "manifold_type": None})
    # Gap dùng 3 phần: tên field nằm ở khoá `field`, KHÔNG nhét vào câu văn.
    g = next(g for g in r["gaps"] if g.get("rule_code") == "R-MFD-ENDPLATE-01")
    assert g["field"] == "manifold_type", g
    assert g.get("options"), "phải liệt kê lựa chọn cho người dùng"
    r2 = _build([("CDM2L32-500Z", 5)], {**MFD_CFG, "manifold_type": "20P, 23P"})
    assert _line(r2, "SY5000-26-21A"), "Type 20P phải ra end plate khác"


def test_khong_ga_manifold_thi_khong_can_gasket():
    """Không gá manifold → không gasket, không end plate.

    Điều kiện là `use_manifold`, KHÔNG phải kiểu cửa van: golden test cho thấy
    máy 23-432 dùng van body-ported mà vẫn có manifold + gasket + end plate.
    """
    r = _build([("CDM2L32-500Z", 5)],
               {**MFD_CFG, "use_manifold": False})
    assert not _line(r, "SY5000-GS-1")
    assert not _line(r, "SY5000-26-20A")


def test_de_manifold_sinh_dung_ma():
    """Đế manifold SS5Y — gap CUỐI CÙNG của engine, giờ sinh được mã.

    5 van → SS5Y5-20-05. Số station là mã 2 chữ số ĐỆM 0 theo catalog trang 44
    ('02 = 2 stations'), không đệm thì ra 'SS5Y5-20-5' — mã không tồn tại.
    """
    r = _build([("CDM2L32-500Z", 5)], {**MFD_CFG})
    mfd = _line(r, "SS5Y5-20-05")
    assert mfd and mfd["qty"] == 1, f"đế manifold: {[l['part_number'] for l in r['lines']]}"
    assert "R-MFD-01" not in {g.get("rule_code") for g in r["gaps"]}
    # không gá manifold → không đế, không gasket, không end plate
    solo = _build([("CDM2L32-500Z", 5)], {**MFD_CFG, "use_manifold": False})
    assert not _line(solo, "SS5Y5-20-05")
    assert not _line(solo, "SY5000-GS-1")
    for g in r["gaps"] + solo["gaps"]:
        assert g.get("reason") and g.get("rationale"), f"gap thiếu lý do: {g}"


def test_so_station_theo_so_van():
    """Đế phải đủ station cho số van: 3 van → 03, 12 van → 12."""
    for n, want in ((3, "SS5Y5-20-03"), (12, "SS5Y5-20-12")):
        r = _build([("CDM2L32-500Z", n)], {**MFD_CFG})
        assert _line(r, want), f"{n} van → {want}, có {[l['part_number'] for l in r['lines']]}"


def test_ma_khong_parse_duoc_thi_bao():
    r = _build([("CDM2X99-500Z", 1)])
    # mã liên quan nằm ở khoá `subject` của vấn đề 3 phần
    g = next((g for g in r["gaps"] if g.get("subject") == "CDM2X99-500Z"), None)
    assert g, f"mã sai phải vào gap: {r['gaps']}"
    assert g["rule_code"] == "R-PARSE-00", g
    assert "Mã tự do" in (g.get("fix") or ""), \
        "phải chỉ đúng cách sửa: sửa mã, hoặc bật Mã tự do"


def test_tinh_toan():
    """Lực và lưu lượng — ø32 @ 0.5 MPa."""
    r = _build([("CDM2L32-500Z", 5)])
    c = r["calc"][0]
    assert 395 < c["thrust_push_N"] < 410, c["thrust_push_N"]   # π/4·32²·0.5 ≈ 402 N
    assert c["rod_mm"] == 12.0                                  # PDF trang 14
    assert c["piston_speed_mm_s"] == 667                        # 500mm / 0.75s
    assert r["system"]["required_flow_lpm"] > r["system"]["total_flow_lpm"]


def test_prune_projects():
    """Dọn phương án cũ: DB không phình vô hạn, và xoá theo cả bảng con.

    Lỗi gốc: mỗi lần dựng BOM ghi một dòng `project` mà không bao giờ xoá —
    máy phát triển lên 35.607 project / 268.531 dòng project_output.
    """
    con = db.connect()
    bom.seed_rules(con)
    for i in range(5):
        bom.build(con, [("CDM2L32-500Z", 1)], {"tube_total_m": 20},
                  project_name=f"prune-{i}")
    n0 = con.execute("select count(*) from project").fetchone()[0]
    assert n0 >= 5, n0

    ids_before = [r[0] for r in con.execute("select id from project order by id desc limit 3")]
    removed = bom.prune_projects(con, keep=3)
    con.commit()

    n1 = con.execute("select count(*) from project").fetchone()[0]
    assert n1 == 3, f"giữ 3 mà còn {n1}"
    assert removed == n0 - 3, f"báo xoá {removed}, thực xoá {n0 - 3}"

    # giữ đúng 3 bản MỚI NHẤT, không phải 3 bản bất kỳ
    ids_after = [r[0] for r in con.execute("select id from project order by id desc")]
    assert ids_after == ids_before, f"{ids_after} != {ids_before}"

    # on delete cascade phải dọn bảng con — nếu pragma foreign_keys tắt thì
    # project_output còn dòng mồ côi mà không có lỗi nào báo ra.
    for t in ("project_output", "project_input", "project_warning"):
        orphan = con.execute(
            f"select count(*) from {t} where project_id not in (select id from project)"
        ).fetchone()[0]
        assert orphan == 0, f"{t} còn {orphan} dòng mồ côi"

    # keep=0 = tắt dọn, KHÔNG phải xoá hết
    assert bom.prune_projects(con, keep=0) == 0
    assert con.execute("select count(*) from project").fetchone()[0] == 3
    con.close()


def test_build_tu_dong_don():
    """build() tự dọn — không cần ai gọi tay prune_projects()."""
    con = db.connect()
    bom.seed_rules(con)
    con.execute("delete from project")
    con.commit()
    keep = 4
    old = bom.PROJECT_KEEP
    bom.PROJECT_KEEP = keep
    try:
        for i in range(keep + 6):
            bom.build(con, [("CDM2L32-500Z", 1)], {"tube_total_m": 20},
                      project_name=f"auto-{i}")
        n = con.execute("select count(*) from project").fetchone()[0]
        assert n == keep, f"hạn mức {keep} mà DB có {n} phương án"
    finally:
        bom.PROJECT_KEEP = old
        con.close()


def test_engine_tu_chon_loai_van_khong_hoi():
    """Mục 6 của spec: engine TỰ chọn loại van theo tác động, không bắt khai.

    Trước đây để trống valve_function là gap. Nay tác động kép → van 5/2 (double),
    tác động đơn → 3/2 (single). Người dùng override thì override thắng.
    """
    r = _build([("CDM2L32-500Z", 4)],
               {"tube_total_m": 60, "tube_roll_length_m": 20, "tube_color": "BU",
                "main_line_port_size": "3/8", "frl_size": "30"})
    assert not any(g.get("field") == "valve_function" for g in r["gaps"]), \
        f"không được hỏi loại van nữa: {r['gaps']}"
    v = [l for l in r["lines"] if l["layer"] == "valve"]
    assert v, "phải sinh được van"
    auto = [w for w in r["warnings"] if w["code"] == "AUTO_VALVE_FUNCTION"]
    assert auto, "tự quyết thì phải NÓI RA để người dùng kiểm lại"


def test_engine_tu_chon_co_van_tu_luu_luong():
    """Cỡ van suy từ lưu lượng qua bảng dẫn nạp âm, không hỏi người dùng.

    Kiểm chứng bằng máy thật: 4× CDM2L32-500Z cần 1065 L/min ANR → SY5000, đúng
    cỡ van BOM máy 23-432 dùng.
    """
    r = _build([("CDM2L32-500Z", 4)],
               {"tube_total_m": 60, "tube_roll_length_m": 20, "tube_color": "BU",
                "main_line_port_size": "3/8", "frl_size": "30"})
    assert r["project"]["valve_series_size"] == "SY5000", r["project"]["valve_series_size"]
    assert not any(g.get("field") == "valve_series_size" for g in r["gaps"])
    w = next((w for w in r["warnings"] if w["code"] == "AUTO_VALVE_SIZE"), None)
    assert w and "SY5000" in w["message"], w
    # phải mang theo nguồn tra cứu
    assert "trang" in (w.get("rationale") or ""), w


def test_khai_tay_thi_thang_engine_tu_tinh():
    """Người dùng khai cỡ van thì engine KHÔNG ghi đè."""
    r = _build([("CDM2L32-500Z", 4)],
               {"tube_total_m": 60, "tube_roll_length_m": 20, "tube_color": "BU",
                "main_line_port_size": "3/8", "frl_size": "30",
                "valve_series_size": "SY7000"})
    assert r["project"]["valve_series_size"] == "SY7000"
    assert not any(w["code"] == "AUTO_VALVE_SIZE" for w in r["warnings"])


def test_gap_ngan_gon_chi_tiet_vao_detail():
    """Phần chính phải NGẮN; catalog/số trang/logic đẩy hết vào detail."""
    r = _build([("CDM2L32-500Z", 5)], {"tube_total_m": 60})
    g = next(g for g in r["gaps"] if g.get("rule_code") == "R-FRL-01")
    assert len(g["what"]) < 60, f"câu chính quá dài: {g['what']}"
    assert g["field"] and g["fix"]
    # rationale gốc của luật dài 600+ ký tự — phải nằm ở detail, không ở phần chính
    assert len(g.get("detail") or "") > 200, "chi tiết dài phải được giữ ở detail"
    assert "trang" not in g["what"], "số trang catalog không được vào câu chính"


def test_van_suy_doan_thi_ha_tin_cay():
    """Loại van do engine SUY → dòng van phải hạ tin cậy xuống ≤50%.

    Đo được trên máy 23-432: engine suy ra 17 van `double`, thực tế 5 single +
    2 double + 4 3-pos. Cảnh báo chung không sửa được số lượng sai, nên phải hiện
    độ tin cậy thấp NGAY TRÊN DÒNG để người ký BOM thấy chỗ cần kiểm.
    """
    cfg = {"tube_total_m": 60, "tube_roll_length_m": 20, "tube_color": "BU",
           "main_line_port_size": "3/8", "frl_size": "30"}
    guessed = _build([("CDM2L32-500Z", 4)], cfg)
    told = _build([("CDM2L32-500Z", 4, {"valve_function": "double"})], cfg)
    gv = [l for l in guessed["lines"] if l["layer"] == "valve"]
    tv = [l for l in told["lines"] if l["layer"] == "valve"]
    assert gv and tv
    assert gv[0]["confidence"] <= 0.5, f"suy đoán mà tin cậy {gv[0]['confidence']}"
    assert tv[0]["confidence"] > 0.5, f"bạn khai mà tin cậy {tv[0]['confidence']}"


def test_requires_khong_bi_lach():
    """Ràng buộc `requires` phải chặn ở CẢ HAI nhánh chọn option.

    Hai lỗi im lặng đã sửa, cùng hậu quả: sinh ra mã KHÔNG TỒN TẠI mà không báo.
      1. `opts = ok_opts or opts` — lọc xong còn rỗng thì quay lại dùng TOÀN BỘ
         danh sách, tức bỏ qua ràng buộc.
      2. nhánh "chỉ định thẳng mã option" đi TRƯỚC phần kiểm requires nên lách
         được: want={"port_size":"M5"} khớp đúng mã "M5" → sinh AN40-M5, trong
         khi catalog trang 1195 ghi M5 chỉ dùng với thân AN05.
    """
    con = db.connect()
    row = con.execute("select id from series where catalog_id='AN-E'").fetchone()
    if not row:
        con.close()
        return                                  # bản phát hành chưa có họ AN
    sid = row["id"]
    from engine import generate
    okc = generate.generate(con, sid, {"body_size": 15, "port_size": "1/4"})
    assert okc.get("part_number") == "AN15-02", okc
    okm = generate.generate(con, sid, {"body_size": 5, "port_size": "M5"})
    assert okm.get("part_number") == "AN05-M5", okm
    # cặp không tồn tại — phải GAP, không được nặn ra mã
    for want in ({"body_size": 40, "port_size": "M5"},
                 {"body_size": 5, "port_size": "1/2"}):
        bad = generate.generate(con, sid, want)
        assert not bad.get("part_number"), f"sinh mã không tồn tại: {bad}"
        assert bad.get("gap"), bad
    con.close()


def test_an_doc_duoc_ma_trong_bom_that():
    """AN15-02 là mã CÓ THẬT trong BOM máy 23-432 — phải parse được."""
    con = db.connect()
    from engine import parser as P
    r = P.parse(con, "AN15-02")
    con.close()
    if not con:
        return
    assert r.get("ok"), r
    a = r.get("attrs") or {}
    assert a.get("port_size") == "1/4", a
    # dẫn nạp âm đọc từ bảng Performance cùng trang — để sau engine chọn cỡ giảm
    # âm theo lưu lượng xả thay vì hỏi
    assert a.get("sonic_C") == 3, a


# ── engine TỰ TÍNH cỡ AC từ đồ thị lưu lượng đã số hoá ──────────────────────
# Trước đây `frl_size` bắt người dùng khai vì "catalog chỉ in dạng ĐỒ THỊ".
# db/seed/charts/ac-flow.yaml (qua cổng tests/test_chart.py) đã số hoá xong.
FRL_AUTO = {"tube_total_m": 60, "main_line_port_size": "3/8",
            "valve_series_size": "SY5000", "supply_pressure_mpa": 1.0}


def test_co_ac_engine_tu_tinh_khi_co_ap_nguon():
    # frl_series -D để khớp thế hệ của đồ thị; ca lệch thế hệ có test riêng
    r = _build([("CDM2B40-150AZ", 4)], dict(FRL_AUTO, frl_series="AC-D-E"))
    info = next((w for w in r.get("warnings") or []
                 if w.get("code") == "AUTO_FRL_SIZE"), None)
    assert info, f"phải nói ra cỡ AC engine tự tính: {r.get('warnings')}"
    assert "Cỡ AC:" in info["message"], info
    # lý do phải nêu ĐỦ ba yếu tố, không chỉ ra con số
    for kw in ("L/min", "áp vào", "đặt"):
        assert kw in info["rationale"], f"thiếu '{kw}' trong lý do: {info['rationale']}"
    assert any(l["layer"] == "air_prep" for l in r["lines"]), "phải có dòng FRL"


def test_do_thi_khac_the_he_thi_canh_bao_khong_bao_info():
    """Đồ thị -D dùng để chọn mã -A là giả thiết chưa kiểm — phải nói ra."""
    r = _build([("CDM2B40-150AZ", 4)], dict(FRL_AUTO, frl_series="AC-A-E"))
    w = next((x for x in r.get("warnings") or []
              if x.get("code") == "AUTO_FRL_SIZE_OTHER_GEN"), None)
    assert w, f"phải cảnh báo lệch thế hệ: {[x.get('code') for x in r['warnings']]}"
    assert w["severity"] == "warn", w
    assert "-D" in w["rationale"] and "ES40-60-AC10-A" in w["rationale"], w["rationale"]


def test_dung_the_he_khop_thi_khong_canh_bao():
    r = _build([("CDM2B40-150AZ", 4)], dict(FRL_AUTO, frl_series="AC-D-E"))
    codes = [x.get("code") for x in r.get("warnings") or []]
    assert "AUTO_FRL_SIZE" in codes, codes
    assert "AUTO_FRL_SIZE_OTHER_GEN" not in codes, codes


def test_thieu_ap_nguon_thi_hoi_ap_nguon_khong_hoi_co_ac():
    """Thiếu dữ liệu thì hỏi ĐÚNG thứ người dùng biết, không bắt tra catalog."""
    cfg = dict(FRL_AUTO)
    cfg.pop("supply_pressure_mpa")
    r = _build([("CDM2B40-150AZ", 4)], cfg)
    g = next((x for x in r.get("gaps") or []
              if x.get("field") == "supply_pressure_mpa"), None)
    assert g, f"phải báo gap ở áp nguồn: {[x.get('field') for x in r.get('gaps') or []]}"
    assert not any(x.get("field") == "frl_size" for x in r.get("gaps") or []), \
        "không được hỏi cỡ AC khi nguyên nhân thật là thiếu áp nguồn"
    assert "áp vào" in (g.get("detail") or ""), g


def test_co_ac_nguoi_dung_khai_khong_bi_ghi_de():
    cfg = dict(FRL_AUTO)
    cfg["frl_size"] = "60"
    r = _build([("CDM2B40-150AZ", 1)], cfg)
    assert not any(w.get("code") == "AUTO_FRL_SIZE" for w in r.get("warnings") or []), \
        "người dùng đã khai thì engine KHÔNG được tự quyết rồi báo"


def test_luu_luong_lon_thi_bao_vuot_dai_chu_khong_ngoai_suy():
    """Vượt dải đã số hoá phải BÁO, không được kéo dài đường cong."""
    from engine import chart
    size, why = chart.pick_frl_size(200000, 0.5, 1.0)
    assert size is None, f"200.000 L/min không được ra cỡ nào: {size}"
    assert "vượt cả cỡ lớn nhất" in why, why


# ── VÒNG B: sụt áp của phụ kiện FRL cộng vào bài toán chọn cỡ ───────────────
def test_sut_ap_phu_kien_lam_len_co():
    """Tra dầu nối SAU điều áp → sụt thêm áp → có lúc phải lên cỡ."""
    from engine import chart
    a, _ = chart.pick_frl_size(3000, 0.5, 1.0, "AC")
    b, why = chart.pick_frl_size(3000, 0.5, 1.0, "AC", lubricator=True)
    assert a and b, (a, b)
    assert int(b) > int(a), f"có tra dầu phải cần cỡ ≥: {a} → {b}"
    assert "AL" in why and "sụt" in why, why


def test_thieu_so_sut_ap_thi_bao_dung_nguyen_nhan():
    """Không được báo 'vượt cỡ lớn nhất' khi nguyên nhân là thiếu số phụ kiện."""
    from engine import chart
    size, why = chart.pick_frl_size(1000, 0.5, 1.0, "AC", mist_separator=True)
    assert size is None
    assert "PHỤ KIỆN" in why and "không phải vì bộ điều áp" in why, why


def test_sut_ap_khong_ngoai_suy():
    from engine import chart
    y, why = chart.frl_drop("50", 9000, "AF")
    assert y is None, f"9000 L/min ngoài dải AF50 đã số hoá: {y}"
    assert "NGOÀI khoảng" in why or "VƯỢT dải" in why, why


def test_sut_ap_bao_tren_tang_don_dieu():
    """Bao trên phải tăng — số giảm là ước sụt áp thấp hơn thực tế."""
    from engine import chart
    bad = []
    for cid, ch in chart.load_all().items():
        if not cid.startswith("frl_drop_"):
            continue
        pts = ch["series"][0]["points"]
        if any(b[1] < a[1] for a, b in zip(pts, pts[1:])):
            bad.append(ch["model_label"])
    assert not bad, f"bao trên GIẢM ở: {bad}"


def test_co_cua_suy_tu_do_thi_khong_hoi_rieng():
    """Cỡ cửa đi kèm kết luận chọn cỡ, vì đồ thị được đo ở một cỡ cửa xác định."""
    cfg = dict(FRL_AUTO, frl_series="AC-D-E")
    cfg.pop("main_line_port_size")
    r = _build([("CDM2B40-150AZ", 4)], cfg)
    w = next((x for x in r["warnings"] if x.get("code") == "AUTO_MAIN_PORT"), None)
    assert w, f"phải tự suy cỡ cửa: {[x.get('code') for x in r['warnings']]}"
    assert "đo ở" in w["rationale"], w["rationale"]
    assert not any(g.get("field") == "main_line_port_size" for g in r["gaps"]), r["gaps"]


def test_cua_nho_hon_do_thi_thi_canh_bao_lac_quan():
    r = _build([("CDM2B40-150AZ", 4)],
               dict(FRL_AUTO, frl_series="AC-D-E", frl_size="40",
                    main_line_port_size="02"))
    w = next((x for x in r["warnings"]
              if x.get("code") == "PORT_SMALLER_THAN_CHART"), None)
    assert w and w["severity"] == "warn", [x.get("code") for x in r["warnings"]]
    assert "LẠC QUAN" in w["message"], w["message"]


def test_cua_khong_co_o_co_engine_chon_thi_nang_co():
    """Cửa là ràng buộc CỨNG của người dùng, cỡ thân thì engine chọn 'nhỏ nhất
    đủ' — nên nâng cỡ, không bế tắc và cũng không bịa mã."""
    r = _build([("CDM2B40-150AZ", 4)],
               dict(FRL_AUTO, frl_series="AC-D-E", main_line_port_size="10"))
    w = next((x for x in r["warnings"]
              if x.get("code") == "FRL_SIZE_RAISED_FOR_PORT"), None)
    assert w, [x.get("code") for x in r["warnings"]]
    frl = next((l["part_number"] for l in r["lines"] if l["layer"] == "air_prep"), None)
    assert frl and frl.startswith("AC50"), f"phải nâng lên cỡ 50: {frl}"
    assert not r["gaps"], r["gaps"]


def test_khong_sinh_ma_khong_ton_tai_theo_bang_how_to_order():
    """Ràng buộc đọc từ bảng How to Order phải CHẶN, không phải cảnh báo suông."""
    from engine import generate as G
    con = db.connect()
    sid = con.execute("select id from series where catalog_id='AC-D-E'").fetchone()["id"]
    # catalog: '01 1/8 V — — — —' · '06 3/4 — — V V —' · '10 1 — — — V V'
    for want, tag in ((({"size": "20", "port_size": "1"}), "Rc1 trên thân 20"),
                      (({"size": "60", "port_size": "3/4"}), "3/4 trên thân 60"),
                      (({"size": "30", "port_size": "1/8"}), "1/8 trên thân 30")):
        g = G.generate(con, sid, dict(want))
        assert not g.get("ok"), f"{tag} không tồn tại mà vẫn sinh: {g.get('part_number')}"
        assert g.get("options"), f"{tag}: phải liệt kê cửa còn lắp được"
    for want, tag in ((({"size": "20", "port_size": "1/4"}), "1/4 trên thân 20"),
                      (({"size": "50", "port_size": "1"}), "Rc1 trên thân 50")):
        g = G.generate(con, sid, dict(want))
        assert g.get("ok"), f"{tag} CÓ thật mà bị chặn: {g}"
    con.close()


def test_khai_du_ca_co_va_cua_thi_van_kiem_luu_luong():
    """Hồi quy: nhánh kiểm lưu lượng từng bị gắn `elif` vào khối kiểm cửa."""
    r = _build([("CDM2B40-150AZ", 8)],
               dict(FRL_AUTO, frl_series="AC-D-E", frl_size="20",
                    main_line_port_size="02"))
    assert any(x.get("code") == "FRL_SIZE_TOO_SMALL" for x in r["warnings"]), \
        [x.get("code") for x in r["warnings"]]


def test_moi_tep_ngu_phap_nap_duoc_tren_db_dung_moi():
    """Dựng DB từ đầu phải nạp được MỌI tệp ngữ pháp.

    Lỗi đã mắc: an.yaml dùng `create_series: true` dạng bool, code gọi thẳng
    cs.get() nên VỠ. Không lộ trong ngày thường vì series AN-E đã có sẵn trong DB
    nên nhánh tạo series không chạy — chỉ vỡ khi dựng lại từ đầu.
    """
    import os
    import tempfile
    from crawler import grammar_seed as GS
    tmp = tempfile.mkdtemp()
    old = os.environ.get("PNEU_DB")
    os.environ["PNEU_DB"] = os.path.join(tmp, "t.db")
    try:
        con = db.init(Path(os.environ["PNEU_DB"]))
        for f in sorted(GS.SEED_DIR.glob("*.yaml")):
            GS.load_file(con, f)        # chỉ cần KHÔNG ném lỗi
        con.close()
    finally:
        if old is None:
            os.environ.pop("PNEU_DB", None)
        else:
            os.environ["PNEU_DB"] = old


def test_AR_D_sinh_lai_dung_ma_that_trong_BOM():
    """Sinh lại ĐÚNG mã khách hàng đã mua — phép kiểm mạnh nhất cho ngữ pháp.

    Bắt được lỗi dấu gạch: gạch đặt ở ô `thread_type` (is_required=0) nên khi ren
    = Rc cả ô bị bỏ, mang theo cả gạch → 'AR3003BE-D' thay vì 'AR30-03BE-D'.
    """
    from engine import generate as G
    con = db.connect()
    sid = con.execute("select id from series where catalog_id='AR-D-E'").fetchone()["id"]
    cases = [
        ({"size": "30", "port_size": "3/8", "mounting": "B",
          "pressure_gauge": "E"}, "AR30-03BE-D"),
        ({"size": "30", "port_size": "3/8", "mounting": "B"}, "AR30-03B-D"),
        ({"size": "30", "port_size": "3/8", "pressure_gauge": "E"}, "AR30-03E-D"),
        ({"size": "30", "port_size": "3/8", "port_standard": "NPT"}, "AR30N-03-D"),
    ]
    try:
        for want, exp in cases:
            got = G.generate(con, sid, dict(want)).get("part_number")
            assert got == exp, f"{want} → {got}, cần {exp}"
    finally:
        con.close()


def test_AR_D_chan_to_hop_khong_co_trong_bang():
    """Ràng buộc đọc từ bảng How to Order tr100 phải CHẶN."""
    from engine import generate as G
    con = db.connect()
    sid = con.execute("select id from series where catalog_id='AR-D-E'").fetchone()["id"]
    try:
        # bảng: '01 1/8 V — — — —' · '10 1 — — — V V' · chân H chỉ có ở 20/30/40
        for want, tag in (({"size": "20", "port_size": "1"}, "Rc1 trên thân 20"),
                          ({"size": "50", "port_size": "3/8"}, "3/8 trên thân 50"),
                          ({"size": "50", "port_size": "3/4",
                            "mounting": "H"}, "chân H trên thân 50")):
            g = G.generate(con, sid, dict(want))
            assert not g.get("ok"), f"{tag} không có trong bảng mà vẫn sinh: {g}"
        # cỡ 25 chỉ có ở thế hệ -B, tệp này là -D
        assert not G.generate(con, sid, {"size": "25", "port_size": "1/4"}).get("ok")
        # ca CÓ THẬT vẫn phải sinh được
        assert G.generate(con, sid, {"size": "30", "port_size": "3/8",
                                     "mounting": "H"}).get("ok")
    finally:
        con.close()


def test_KQ2_chan_to_hop_khong_co_trong_catalog():
    """Ràng buộc rút từ 1366 mã KQ2 catalog LIỆT KÊ, không từ ma trận đánh dấu."""
    from engine import generate as G
    con = db.connect()
    sid = con.execute("select id from series where catalog_id='KQ2-E'").fetchone()["id"]
    base = {"port_standard": "R", "thread_material": "A"}
    try:
        for want, tag in (
                ({"shape": "D", "tube_od": "23", "port_size": "1/4"}, "D ø3.2"),
                ({"shape": "VF", "tube_od": "16", "port_size": "3/8"}, "VF ø16"),
                ({"shape": "H", "tube_od": "02", "port_size": "3/8"}, "ø2 + cửa 3/8")):
            g = G.generate(con, sid, dict(base, **want))
            assert not g.get("ok"), f"{tag} không có trong catalog mà vẫn sinh: {g}"
        for want, exp in (
                ({"shape": "H", "tube_od": "06", "port_size": "1/4"}, "KQ2H06-02A1"),
                ({"shape": "L", "tube_od": "06", "port_size": "1/8",
                  "thread_material": "N"}, "KQ2L06-01N1")):
            got = G.generate(con, sid, dict(base, **want)).get("part_number")
            assert got == exp, f"{want} → {got}, cần {exp}"
    finally:
        con.close()


def test_KQ2_moi_ma_BOM_that_van_parse_duoc():
    """19 mã KQ2 khách hàng đã mua — ràng buộc không được loại mã nào."""
    from engine import parser as P
    con = db.connect()
    try:
        codes = [r["raw_code"] for r in con.execute(
            "select distinct raw_code from bom_line where raw_code like 'KQ2%'")]
        bad = [c for c in codes if not P.parse(con, c).get("ok")]
        assert not bad, f"ràng buộc làm hỏng parse: {bad}"
        assert len(codes) >= 15, len(codes)
    finally:
        con.close()


def test_co_25_khong_con_trong_ngu_phap_AC_D():
    """Catalog -D không có AC25 (grep toàn PDF: 0 lần)."""
    con = db.connect()
    sizes = {r["code"] for r in con.execute(
        """select o.code from code_option o join code_slot cs on cs.id=o.slot_id
           join series s on s.id=cs.series_id
           where s.catalog_id='AC-D-E' and cs.name='size'""")}
    con.close()
    assert "25" not in sizes, sizes


def test_so_do_thi_dò_tu_anh_phai_ha_tin_cay_va_noi_ra():
    """Số dò từ ẢNH kém chính xác hơn vector — không được coi ngang nhau."""
    from engine import chart
    y, note = chart.lookup("frl_flow_awm20_d", 50, "0.7/0.5")
    assert y is not None, note
    assert "DÒ TỪ ẢNH" in note, note
    y2, n2 = chart.lookup("frl_flow_ac30_d", 1000, "1/0.6")
    assert "DÒ TỪ ẢNH" not in n2, n2


def test_moi_bang_do_thi_deu_khai_nguon_kieu():
    from engine import chart
    for cid, ch in chart.load_all().items():
        if cid.startswith("frl_flow_"):
            assert ch.get("source_kind") in ("vector", "raster"), (cid, ch.get("source_kind"))


def test_do_troi_dieu_ap_kiem_duoc_gia_thiet_mot_bac():
    """pick_frl_size giả định đặt thêm 1 bậc 0,1 MPa che được dao động áp nguồn.

    Giờ có số thật để KIỂM giả thiết đó thay vì tin: trôi đo được 0,024–0,033 MPa
    < 0,1 nên giả thiết đứng. Nếu catalog khác cho số lớn hơn, engine phải cảnh báo.
    """
    from engine import chart
    for sz in ("20", "30", "40", "50", "60"):
        d, note = chart.frl_regulation_drift(sz)
        assert d is not None, note
        assert 0 < d < 0.1, f"AC{sz} trôi {d} — bậc 0,1 MPa không còn che nổi"
        assert "BIÊN THAM KHẢO" in note, note


def test_bang_do_on_dinh_phai_kem_dieu_kien():
    """Số của họ này vô nghĩa nếu thiếu điều kiện thử."""
    from engine import chart
    n = 0
    for cid, ch in chart.load_all().items():
        if not cid.startswith("frl_reg_"):
            continue
        n += 1
        c = ch.get("condition") or {}
        assert c.get("set_mpa") and c.get("flow_lpm"), (cid, c)
    assert n >= 15, f"chỉ có {n} bảng độ ổn định"


def test_khong_lan_series_AR_voi_AR_M():
    """'AR20M(K)-D' là series AR…M, KHÁC 'AR20(K)-D' — không được gộp một họ."""
    from engine import chart
    ar = [l for _, _, l in chart.frl_charts("AR")]
    assert ar and all("M(" not in l for l in ar), ar
    assert any("AR20M" in (ch.get("model_label") or "")
               for ch in chart.load_all().values()), "phải có bảng AR…M trong DB"


def test_bang_do_thi_nao_cung_mang_theo_nguon():
    """Mỗi bảng phải tự mang catalog + số trang — nhiều catalog trong một tệp."""
    from engine import chart
    for cid, ch in chart.load_all().items():
        if not cid.startswith("frl_"):
            continue
        assert ch.get("pdf_page"), cid
        assert ch.get("catalog") or (ch.get("source") or {}).get("catalog"), cid


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
