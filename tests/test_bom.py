"""Test engine BOM. Chạy: python3 tests/test_bom.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tmpdb                                # noqa: E402,F401  PHẢI trước crawler.db
from crawler import db                      # noqa: E402
from engine import bom, learn, materialize         # noqa: E402


def _build(inputs, project=None, use_learned=False):
    """use_learned=False mặc định: giữ test TẤT ĐỊNH.

    Tri thức học được lấy từ bảng bom_line trong DB, nên nếu bật thì thêm/bớt một
    BOM là đổi kết quả test — người sửa test về sau sẽ không hiểu vì sao. Phần học
    có test riêng: test_hoc_tu_bom_co_san.
    """
    con = db.connect()
    bom.seed_rules(con)
    res = bom.build(con, inputs, project, project_name="test",
                    use_learned=use_learned)
    con.close()
    return res


def _line(res, pn):
    return next((l for l in res["lines"] if l["part_number"] == pn), None)


def test_bom_5_xylanh():
    """5× CDM2L32-500Z → BOM 4 tầng, số lượng đúng.

    tube_total_m phải khai tường minh: engine không tự ước lượng chiều dài ống
    (mục A3-5 — người dùng bác bỏ giá trị mặc định 3 m/mối nối).

    tube_roll_length_m cũng phải khai: nó thuộc NEED_EVIDENCE trong build() vì
    đoán sai chiều dài cuộn làm lệch SỐ LƯỢNG cuộn (golden test bỏ-ra-một-máy:
    mặc định 20 m cho ra 15 cuộn trong khi thực tế 1 cuộn 200 m). Không khai và
    chưa học được thì engine báo gap — xem test_khong_khai_chieu_dai_ong_thi_bao_gap.
    """
    r = _build([("CDM2L32-500Z", 5)],
               {"tube_total_m": 60, "tube_roll_length_m": 20, "tube_color": "BU"})
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
    assert g and "tube_total_m" in g["reason"], f"gaps: {r['gaps']}"


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
    assert "main_line_port_size" in g["reason"]


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
    assert "FRL_FLOW_UNVERIFIED" in codes, \
        "phải cảnh báo: catalog chỉ cho lưu lượng dạng đồ thị, engine không kiểm được"


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


def test_van_can_khai_loai():
    """LOẠI van phụ thuộc chức năng cơ cấu → engine đòi khai, không đoán.

    Bản trước mặc định "mọi xy-lanh → 5/2 double"; golden test cho thấy một máy
    dùng đồng thời single, double và 3-position nên sai 6/11 dòng van.
    """
    r = _build([("CDM2L32-500Z", 5)], {"tube_total_m": 60})
    g = next(g for g in r["gaps"] if g.get("rule_code") == "R-VLV-01")
    assert "valve_function" in g["reason"], g["reason"]
    assert not any(l["layer"] == "valve" for l in r["lines"])


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
    g = next(g for g in r["gaps"] if g.get("rule_code") == "R-MFD-ENDPLATE-01")
    assert "manifold_type" in g["reason"]
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


def test_hoc_tu_bom_co_san():
    """Học lựa chọn từ BOM đã nhập — đo được trên dữ liệu thật.

    Tín hiệu mạnh nhất: 69 cái speed controller push-lock, nhất quán 100% qua cả
    hai máy. Đây là thứ trước đây tôi hardcode trong DEFAULT_PROJECT.
    """
    con = db.connect()
    if not con.execute("select count(*) from bom_line").fetchone()[0]:
        con.close()
        return                      # DB chưa nhập BOM (bản phát hành) → bỏ qua
    prefs = {p["subject"]: p for p in learn.learn(con)}
    con.close()

    sc = prefs.get("speed_controller_series")
    assert sc, f"không học được họ speed controller: {list(prefs)}"
    assert sc["value"] == "AS1-E", sc
    assert sc["n_conflict"] == 0, f"BOM thật nhất quán 100%, sao có mâu thuẫn: {sc}"
    assert sc["usable"], sc


def test_hoc_khong_ghi_de_cau_hinh_ban_khai():
    """Tri thức học được KHÔNG BAO GIỜ thắng cấu hình khai tường minh.

    Nếu ngược lại thì người dùng mất quyền điều khiển, và mất một cách âm thầm.
    """
    r = _build([("CDM2L32-500Z", 2)],
               {"tube_total_m": 20, "tube_roll_length_m": 20,
                "speed_controller_series": "AS-E-E"},   # cố ý NGƯỢC thói quen
               use_learned=True)
    codes = [l["part_number"] for l in r["lines"]]
    push = [c for c in codes if c.startswith("AS") and c.endswith(("A", "SA"))]
    assert not push, f"tri thức đã ghi đè cấu hình khai tay: {codes}"


def test_khoa_rieng_may_khong_bao_gio_hoc():
    """Khoá phụ thuộc lưu lượng/layout không được xếp vào nhóm thói quen.

    Đoán sai cỡ van hay tổng mét ống là mua sai hàng. Hai máy thật cùng dùng
    SY5000 và ống ø6, nhưng chúng cỡ gần bằng nhau (17 và 16 xy-lanh) nên N=2
    không tách được "thói quen" khỏi "trùng hợp".
    """
    for k in ("valve_series_size", "tube_od_mm", "tube_total_m", "frl_size",
              "valve_mounting", "manifold_type", "main_line_port_size"):
        assert k not in learn.HABIT_KEYS, f"{k} không được coi là thói quen"
        assert k in learn.MACHINE_KEYS, f"{k} phải nằm trong MACHINE_KEYS"


def test_mau_thuan_thi_khong_dung_thay_vi_lay_trung_binh():
    """Mâu thuẫn quá ngưỡng → không dùng. Trung bình của 1 và 14 là 7, số không tồn tại."""
    con = db.connect()
    if not con.execute("select count(*) from bom_line").fetchone()[0]:
        con.close()
        return
    prefs = {p["subject"]: p for p in learn.learn(con)}
    con.close()
    roll = prefs.get("tube_roll_length_m")
    if roll:
        # BOM thật có cả cuộn 200 m và 100 m → mâu thuẫn 2 vs 2
        assert roll["n_conflict"] > 0, roll
        assert not roll["usable"], f"mâu thuẫn ngang nhau mà vẫn dùng: {roll}"


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
