"""Chuẩn hoá cách engine báo vấn đề: 3 phần ngắn, chi tiết dài đẩy vào Debug.

YÊU CẦU (Prompt sửa cách báo lỗi của PneuComplete.md): khi engine gặp vấn đề,
KHÔNG giải thích dài dòng. Chỉ trả về:

    1. Sai ở đâu        → component / field nào thiếu hoặc sai
    2. Cần sửa gì       → chỉ rõ field người dùng cần sửa
    3. Sửa như thế nào  → giá trị hoặc lựa chọn cần nhập

Ví dụ đúng:

    R-VLV-01
    ⚠ Chưa xác định được van cho Cylinder C01
    Sai ở:    → valve_function
    Cần sửa:  → Chọn valve_function cho C01

VÌ SAO PHẢI SỬA: rationale trong rules.yaml dài 3–8 câu, có số trang catalog, có
lịch sử vì sao luật ra đời. Đó là tài liệu cho người BẢO TRÌ, không phải thông báo
cho người ĐANG DỰNG BOM. Trộn hai thứ vào một chỗ thì người dùng phải đọc 8 câu
mới biết cần điền ô nào.

Nguyên tắc kèm theo:
  · Engine đủ dữ liệu tự quyết được thì KHÔNG hỏi.
  · Nhiều vấn đề thì tách từng luật riêng, mỗi luật một khối.
  · Có nhiều lựa chọn thì liệt kê ra để người dùng chọn, không bắt tra catalog.
  · catalog / Cv / AFM / số trang / logic phân tích → chỉ vào `detail`.
"""

# Nhãn tiếng Việt cho các field hay bị thiếu. Người dùng không đọc tên biến.
FIELD_VN = {
    "valve_function": "Loại van",
    "valve_series_size": "Cỡ van",
    "main_line_port_size": "Cỡ cửa đường trục chính",
    "frl_size": "Cỡ bộ xử lý khí (AC)",
    "manifold_type": "Kiểu manifold",
    "tube_total_m": "Tổng mét ống",
    "tube_od_mm": "Đường kính ống",
    "tube_color": "Màu ống",
    "tube_roll_length_m": "Chiều dài cuộn ống",
    "speed_controller_series": "Họ tiết lưu",
    "speed_controller_knob": "Kiểu núm tiết lưu",
    "frl_series": "Thế hệ bộ xử lý khí",
    "pressure_mpa": "Áp suất làm việc",
    "cycle_s": "Chu kỳ",
    "voltage": "Điện áp coil",
    "rod_end_thread": "Ren đầu cần",
    "port_size": "Cỡ cửa khí",
}


def field_vn(f):
    return FIELD_VN.get(f, f)


def problem(rule_code, what, *, field=None, fix=None, how=None, options=None,
            subject=None, detail=None, severity="gap", code=None):
    """Dựng một vấn đề theo đúng 3 phần.

    rule_code : mã luật, vd 'R-VLV-01'
    what      : MỘT câu — sai cái gì. Không giải thích vì sao.
    field     : tên field cần sửa (khoá kỹ thuật)
    fix       : "Cần sửa gì" — mặc định sinh từ field + subject
    how       : "Sửa như thế nào" — giá trị cụ thể cần nhập
    options   : danh sách lựa chọn, nếu có nhiều
    subject   : thiết bị liên quan, vd 'CDM2L32-500Z' hoặc nhãn node 'C01'
    detail    : mọi thứ dài dòng — catalog, Cv, số trang, rationale gốc
    severity  : 'gap' | 'warn' | 'error' | 'info'
    """
    if fix is None and field:
        fix = f"Chọn {field_vn(field)}" + (f" cho {subject}" if subject else "")
    if how is None and options:
        how = " · ".join(str(o) for o in options[:8])
    return {
        "rule_code": rule_code,
        # `code` là ĐỊNH DANH MÁY ĐỌC, ổn định, dùng cho test và cho UI lọc.
        # KHÔNG suy từ `field`: suy như vậy sinh ra mã vô nghĩa kiểu "EDGE.KIND"
        # và đổi mỗi lần đổi nhãn field.
        "code": code or rule_code,
        "severity": severity,
        "subject": subject,
        # ── 3 phần, đây là những gì UI hiển thị ─────────────────────────────
        "what": what,
        "field": field,
        "fix": fix,
        "how": how,
        "options": list(options) if options else None,
        # ── chỉ vào Chi tiết/Debug ──────────────────────────────────────────
        "detail": detail,
    }


def as_gap(p):
    """Đổi sang hình dạng `gaps` mà engine/UI đang dùng, giữ tương thích ngược.

    `reason` là khoá chung của mọi gap trong engine — bỏ nó là UI và test không
    đọc được (đã mắc lỗi này một lần).
    """
    return {**p, "reason": p["what"], "rationale": p.get("detail") or ""}


def as_warning(p):
    return {**p, "code": p.get("code") or p["rule_code"],
            "message": p["what"], "rationale": p.get("detail") or ""}


def render_text(p):
    """Dạng chữ thuần — dùng cho CLI và cho test đọc được kết quả."""
    # dùng .get(): gap đến từ nhiều nguồn, thiếu khoá thì hiện "?" chứ không vỡ
    out = [p.get("rule_code") or "?", f"⚠ {p.get('what') or p.get('reason') or ''}"]
    if p.get("field"):
        out += ["", "Sai ở:", f"→ {p['field']}"]
    if p.get("fix"):
        out += ["", "Cần sửa:", f"→ {p['fix']}"]
    if p.get("how"):
        out += ["", "Sửa như thế nào:", f"→ {p['how']}"]
    return "\n".join(out)
