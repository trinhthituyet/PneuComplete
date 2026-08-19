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


# KHÔNG có bảng đường kính cần hardcode ở đây.
#
# Bản đầu tôi để `{20:8, 25:10, 32:12, 40:14}` — đúng cho CM2 nhưng SAI ÂM THẦM cho
# mọi series khác (CJ2, CQ2, MGP có đường kính cần khác hẳn). Người dùng chỉ ra ở
# mục A3-1: "sẽ có các trường hợp ngoại lệ, hãy đọc catalog".
#
# Giờ `rod_dia_mm` đi theo TỪNG SERIES: parsers/pdf_dim_table.py đọc cột D của bảng
# kích thước, ghi vào attrs của option ô bore, engine/parser.py tự gộp vào attrs khi
# parse mã. Không có số liệu thì KHÔNG tính lực kéo, chứ không đoán.


def thrust_N(bore_mm, pressure_mpa, direction="push", rod_mm=None):
    """Lực đẩy/kéo lý thuyết. Chưa trừ hiệu suất ma sát (thực tế ~0.85-0.9).

    Lực kéo cần đường kính cần; không có thì trả None (không đoán).
    """
    if direction == "push":
        return piston_area_mm2(bore_mm) * pressure_mpa   # mm² × MPa = N
    if not rod_mm:
        return None
    return rod_area_mm2(bore_mm, rod_mm) * pressure_mpa


def air_per_cycle_L(bore_mm, stroke_mm, pressure_mpa, rod_mm=None, double_acting=True):
    """Khí tiêu thụ 1 chu kỳ, quy về điều kiện khí quyển (L ANR).

    Không biết đường kính cần thì coi rod = 0 cho chiều về — kết quả HƠI CAO hơn
    thực tế (an toàn khi chọn cỡ FRL), và `summary()` ghi rõ giả định này.
    """
    ratio = (pressure_mpa * 1000 + ATM_KPA) / ATM_KPA
    push = piston_area_mm2(bore_mm) * stroke_mm / 1e6          # L (dm³)
    if not double_acting:
        return push * ratio
    pull = rod_area_mm2(bore_mm, rod_mm or 0) * stroke_mm / 1e6
    return (push + pull) * ratio


def consumption_lpm(bore_mm, stroke_mm, pressure_mpa, cycle_s, count=1, rod_mm=None):
    per_cycle = air_per_cycle_L(bore_mm, stroke_mm, pressure_mpa, rod_mm)
    return per_cycle * (60.0 / cycle_s) * count


def piston_speed_mm_s(stroke_mm, stroke_time_s):
    return stroke_mm / stroke_time_s if stroke_time_s else None


def summary(bore_mm, stroke_mm, pressure_mpa, cycle_s, count, safety=1.5, rod_mm=None):
    """rod_mm phải do người gọi truyền vào, lấy từ attrs của mã hàng."""
    rod = rod_mm
    # 1 chu kỳ = đi + về; thời gian mỗi chiều lấy nửa chu kỳ
    speed = piston_speed_mm_s(stroke_mm, cycle_s / 2.0)
    flow = consumption_lpm(bore_mm, stroke_mm, pressure_mpa, cycle_s, count, rod)
    return {
        "bore_mm": bore_mm, "rod_mm": rod, "stroke_mm": stroke_mm,
        "pressure_mpa": pressure_mpa, "cycle_s": cycle_s, "count": count,
        "thrust_push_N": round(thrust_N(bore_mm, pressure_mpa, "push"), 1),
        "thrust_pull_N": (round(thrust_N(bore_mm, pressure_mpa, "pull", rod), 1)
                          if rod else None),
        "air_per_cycle_L": round(air_per_cycle_L(bore_mm, stroke_mm, pressure_mpa, rod), 3),
        "total_flow_lpm": round(flow, 1),
        "required_flow_lpm": round(flow * safety, 1),
        "piston_speed_mm_s": round(speed, 0) if speed else None,
        "assumptions": [
            f"đường kính cần ø{rod} mm (đọc từ bảng kích thước của series)" if rod else
            "CHƯA BIẾT đường kính cần → không tính lực kéo; khí tiêu thụ tính hơi CAO "
            "hơn thực tế (an toàn khi chọn FRL)",
            "lực lý thuyết, chưa trừ ma sát (thực tế còn ~85–90%)",
            f"1 chu kỳ = đi + về, mỗi chiều {cycle_s/2:.2f} s",
            f"hệ số đồng thời {safety} khi chọn cỡ FRL",
        ],
    }
