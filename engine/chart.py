"""Tra cứu đồ thị/bảng đã số hoá từ catalog (mục 7 của prompt sơ đồ đấu nối).

VÌ SAO CÓ: nhiều giá trị chỉ có trong catalog dưới dạng ĐỒ THỊ hoặc BẢNG ảnh —
lưu lượng theo áp suất, dẫn nạp âm theo cỡ van, đồ thị chọn cỡ FRL. Trước đây
engine bó tay và đẩy sang `NEEDS_INPUT`, bắt người dùng tự tra catalog rồi gõ vào.

Số hoá được thì engine tự tra. Ba nguyên tắc:

  1. KHÔNG NGOẠI SUY. Ngoài khoảng đã số hoá thì báo gap, không kéo dài đường
     cong. Ngoại suy sai cỡ van là sụt áp khi nhiều xy-lanh chạy cùng lúc.
  2. MANG THEO NGUỒN. Mỗi bảng có catalog + số trang + confidence, và giá trị tra
     ra phải mang theo chúng để hiện trong rationale — giống cơ chế của rules.yaml.
  3. `needs_review: true` thì vẫn dùng được nhưng phải HẠ tin cậy và nói rõ là
     đang chờ người đối chiếu. Bảng đọc từ PDF gộp hàng thì không thể coi như đã
     chắc.
"""
from engine import conf
from crawler import db

CHART_DIR = db.ROOT / "db" / "seed" / "charts"

_cache = None


def load_all():
    """Đọc mọi bảng trong db/seed/charts/. Thiếu thư mục thì trả rỗng, không lỗi."""
    global _cache
    if _cache is not None:
        return _cache
    out = {}
    if CHART_DIR.is_dir():
        for f in sorted(CHART_DIR.glob("*.yaml")):
            try:
                d = conf.load(f)
            except Exception:
                continue                      # một bảng hỏng không được chặn cả engine
            if isinstance(d, dict) and d.get("chart_id"):
                out[d["chart_id"]] = d
    _cache = out
    return out


def get(chart_id):
    return load_all().get(chart_id)


def _points(chart, series_label=None):
    for s in chart.get("series") or []:
        if series_label is None or s.get("label") == series_label:
            return [(p[0], p[1]) for p in (s.get("points") or [])]
    return []


def lookup(chart_id, x, series_label=None):
    """Tra y theo x. Trả (y, note) — y=None nghĩa là KHÔNG tra được.

    note luôn có nội dung để engine đưa vào rationale/detail.
    """
    ch = get(chart_id)
    if not ch:
        return None, f"chưa số hoá bảng '{chart_id}'"
    pts = _points(ch, series_label)
    if not pts:
        return None, f"bảng '{chart_id}' không có điểm dữ liệu"

    src = ch.get("source") or {}
    where = f"{src.get('catalog', '?')} trang {src.get('pdf_page', '?')}"
    conf_s = ch.get("confidence")
    tag = f"tra {where}"
    if ch.get("needs_review"):
        tag += " (CHỜ NGƯỜI ĐỐI CHIẾU)"

    # bảng rời rạc: khớp đúng khoá, không nội suy
    if ch.get("kind") == "discrete":
        for kx, ky in pts:
            if str(kx) == str(x):
                return ky, tag
        return None, f"{tag}: không có mục '{x}' trong bảng"

    # bảng liên tục: nội suy tuyến tính, KHÔNG ngoại suy
    try:
        xs = [(float(a), float(b)) for a, b in pts]
    except (TypeError, ValueError):
        return None, f"bảng '{chart_id}' có điểm không phải số"
    xs.sort()
    xv = float(x)
    if xv < xs[0][0] or xv > xs[-1][0]:
        return None, (f"{tag}: giá trị {xv} nằm NGOÀI khoảng đã số hoá "
                      f"[{xs[0][0]}–{xs[-1][0]}] — engine không ngoại suy")
    for (x1, y1), (x2, y2) in zip(xs, xs[1:]):
        if x1 <= xv <= x2:
            y = y1 if x2 == x1 else y1 + (y2 - y1) * (xv - x1) / (x2 - x1)
            note = tag + (" · nội suy 2 điểm" if x1 != xv != x2 else "")
            if conf_s:
                note += f" · tin cậy {conf_s:.0%}"
            return y, note
    return None, f"{tag}: không tra được"


# ── dùng riêng cho chọn cỡ van ───────────────────────────────────────────────

def valve_flow_capacity_lpm(size, pressure_mpa):
    """Trần lưu lượng (L/min ANR) của một cỡ van ở áp suất cho trước.

    Dùng định nghĩa ISO 6358 của dẫn nạp âm C ở chế độ chảy tắc:
        q [dm3/s ANR] = C × p1 [bar abs]
    Công thức này ghi trong db/seed/charts/sy-flow.yaml kèm nguồn.
    """
    C, note = lookup("sy_sonic_conductance", size, "capacity")
    if C is None:
        return None, note
    p1_bar_abs = float(pressure_mpa) * 10.0 + 1.013
    return 60.0 * float(C) * p1_bar_abs, f"{note} · C={C} dm³/(s·bar)"


def valve_sizes():
    """Các cỡ van đã số hoá, thứ tự từ nhỏ tới lớn theo C."""
    ch = get("sy_sonic_conductance")
    if not ch:
        return []
    return [k for k, _ in sorted(_points(ch, "capacity"), key=lambda p: float(p[1]))]


def pick_valve_size(required_lpm, pressure_mpa):
    """Cỡ van NHỎ NHẤT đủ lưu lượng. Trả (size, note) — size=None nếu không đủ dữ liệu.

    required_lpm đã bao gồm hệ số đồng thời do bom.py nhân sẵn.
    """
    if not required_lpm:
        return None, "chưa tính được lưu lượng cần cấp"
    tried = []
    for size in valve_sizes():
        cap, note = valve_flow_capacity_lpm(size, pressure_mpa)
        if cap is None:
            continue
        tried.append((size, round(cap)))
        if cap >= float(required_lpm):
            return size, (f"cần {round(float(required_lpm))} L/min ANR, {size} chịu "
                          f"{round(cap)} L/min → chọn cỡ nhỏ nhất thoả · {note}")
    if tried:
        big = tried[-1]
        return None, (f"cần {round(float(required_lpm))} L/min ANR, vượt cả cỡ lớn nhất "
                      f"đã số hoá ({big[0]} chịu {big[1]} L/min). Cần chia mạch hoặc "
                      f"số hoá thêm cỡ van lớn hơn.")
    return None, "chưa số hoá bảng lưu lượng van"
