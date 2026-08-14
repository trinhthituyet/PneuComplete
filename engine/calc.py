"""Tính toán kỹ thuật khí nén. Công thức cơ bản, đơn vị SI, ghi rõ giả định.

Mọi hàm trả kèm `assumptions` để engine đưa vào phần giải thích của BOM —
người dùng phải thấy được con số dựa trên giả định nào.
"""
import math

ATM_KPA = 101.325          # áp suất khí quyển, kPa


def rod_area_mm2(bore_mm, rod_mm):
    return math.pi / 4 * (bore_mm ** 2 - rod_mm ** 2)


def piston_area_mm2(bore_mm):
    return math.pi / 4 * bore_mm ** 2


def rod_dia_mm(bore_mm):
    """Đường kính cần theo bore, họ CM2.

    ĐỌC TRỰC TIẾP từ PDF 7-3-2-p0231-0332-CM2_en.pdf trang 14, bảng kích thước
    cột D (map cột theo toạ độ x của header: D ở x=122).

    ⚠ CẦN XÁC NHẬN (mục A3-1): tôi hiểu cột 'D' là đường kính cần, nhưng không
    xem được bản vẽ nên chưa chắc 100%. Bản trước tôi ghi bore 40 → 16 theo trí
    nhớ; bảng thật ghi 14. Sai chỗ này làm lệch LỰC KÉO (không ảnh hưởng lực đẩy).
    """
    table = {20: 8.0, 25: 10.0, 32: 12.0, 40: 14.0}
    return table.get(int(bore_mm))


def thrust_N(bore_mm, pressure_mpa, direction="push", rod_mm=None):
    """Lực đẩy/kéo lý thuyết. Chưa trừ hiệu suất ma sát (thực tế ~0.85-0.9)."""
    if direction == "push":
        a = piston_area_mm2(bore_mm)
    else:
        rod_mm = rod_mm or rod_dia_mm(bore_mm) or 0
        a = rod_area_mm2(bore_mm, rod_mm)
    return a * pressure_mpa          # mm² × MPa = N


def air_per_cycle_L(bore_mm, stroke_mm, pressure_mpa, rod_mm=None, double_acting=True):
    """Khí tiêu thụ 1 chu kỳ, quy về điều kiện khí quyển (L ANR)."""
    ratio = (pressure_mpa * 1000 + ATM_KPA) / ATM_KPA
    push = piston_area_mm2(bore_mm) * stroke_mm / 1e6          # L (dm³)
    if not double_acting:
        return push * ratio
    rod_mm = rod_mm or rod_dia_mm(bore_mm) or 0
    pull = rod_area_mm2(bore_mm, rod_mm) * stroke_mm / 1e6
    return (push + pull) * ratio


def consumption_lpm(bore_mm, stroke_mm, pressure_mpa, cycle_s, count=1, rod_mm=None):
    per_cycle = air_per_cycle_L(bore_mm, stroke_mm, pressure_mpa, rod_mm)
    return per_cycle * (60.0 / cycle_s) * count


def piston_speed_mm_s(stroke_mm, stroke_time_s):
    return stroke_mm / stroke_time_s if stroke_time_s else None


def summary(bore_mm, stroke_mm, pressure_mpa, cycle_s, count, safety=1.5):
    rod = rod_dia_mm(bore_mm)
    # 1 chu kỳ = đi + về; thời gian mỗi chiều lấy nửa chu kỳ
    speed = piston_speed_mm_s(stroke_mm, cycle_s / 2.0)
    flow = consumption_lpm(bore_mm, stroke_mm, pressure_mpa, cycle_s, count, rod)
    return {
        "bore_mm": bore_mm, "rod_mm": rod, "stroke_mm": stroke_mm,
        "pressure_mpa": pressure_mpa, "cycle_s": cycle_s, "count": count,
        "thrust_push_N": round(thrust_N(bore_mm, pressure_mpa, "push"), 1),
        "thrust_pull_N": round(thrust_N(bore_mm, pressure_mpa, "pull", rod), 1),
        "air_per_cycle_L": round(air_per_cycle_L(bore_mm, stroke_mm, pressure_mpa, rod), 3),
        "total_flow_lpm": round(flow, 1),
        "required_flow_lpm": round(flow * safety, 1),
        "piston_speed_mm_s": round(speed, 0) if speed else None,
        "assumptions": [
            f"đường kính cần ø{rod} mm (PDF CM2 trang 14)" if rod else
            "chưa biết đường kính cần → lực kéo chưa tính được",
            "lực lý thuyết, chưa trừ ma sát (thực tế còn ~85–90%)",
            f"1 chu kỳ = đi + về, mỗi chiều {cycle_s/2:.2f} s",
            f"hệ số đồng thời {safety} khi chọn cỡ FRL",
        ],
    }
