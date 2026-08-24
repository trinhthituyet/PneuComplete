"""Số hoá đồ thị catalog TỰ ĐỘNG từ vector trong PDF — không click tay.

VÌ SAO LÀM ĐƯỢC: đồ thị trong catalog SMC được vẽ bằng VECTOR, không phải ảnh
raster. `pdftocairo -svg` cho đường cong, `pdftotext -bbox-layout` cho nhãn trục
kèm toạ độ. Có hai thứ đó là đủ:

    nhãn trục (text + toạ độ)  →  hiệu chuẩn pixel → giá trị thật
    đường cong (toạ độ pixel)  →  áp hiệu chuẩn   → tập điểm dữ liệu

Spec §7 của prompt sơ đồ đề xuất công cụ click tay từng điểm. Cách này chính xác
hơn (không lệ thuộc tay người) và chạy được trên cả trăm đồ thị.

    python3 -m parsers.pdf_chart <pdf> <trang>     # xem trích được gì
    python3 -m parsers.pdf_chart --scan <pdf>      # tìm trang có đồ thị
    python3 tests/test_chart.py                    # CỔNG 12 tiêu chí + 7 đối chứng âm
    python3 -m parsers.chart_yaml --write          # sinh YAML (tự gọi cổng)

TRẠNG THÁI (đo được, 11 trang / 5 catalog trong ground truth):

    họ đồ thị            ô vector   đã số hoá   ghi ra YAML
    lưu lượng → áp ra          24          23   ac-flow.yaml   23 model/198 đường
    lưu lượng → sụt áp         23          22   frl-drop.yaml  22 model/94 đk
    áp vào   → áp ra           24           0   TỪ CHỐI (chưa có ground truth)
    chưa nhận dạng được         4           0
    ─ trang ẢNH RASTER          9           0   phương pháp này không đọc được

engine.chart dùng chúng để tự chọn cỡ AC và cộng sụt áp của phụ kiện nối sau bộ
điều áp. Cổng: tests/test_chart.py — 17 tiêu chí + 11 đối chứng âm.

── Ý CHÍNH VỀ THIẾT KẾ: NHÃN TRỤC ĐỊNH NGHĨA Ô, KHÔNG PHẢI ĐƯỜNG CONG ────────
Bản đầu suy ô từ CỤM ĐƯỜNG CONG rồi cộng offset đo trên đúng một trang để tìm
nhãn. Mỗi lần sửa bộ lọc đường cong là bbox đổi → mọi vùng nhãn lệch → cả trang
mất nhãn. Xảy ra BA lần (lọc lưới, tách subpath, hạ ngưỡng số điểm); vòng lặp đó
không hội tụ, và nó đúng là lớp lỗi "mainY=380 cứng" đã phê phán ở prototype.

Đảo chiều phụ thuộc (_axes): nhãn trục là text có toạ độ, do catalog đặt, KHÔNG
phụ thuộc cách trích đường cong — và nó chính là mốc hiệu chuẩn. Nên để nó định
nghĩa ô, rồi GÁN đường cong vào ô theo điểm đầu. Không còn hằng số nào theo trang.

── BỐN LỚP PHẢI BÓC, mỗi lớp tôi đều đoán sai một lần trước khi đo ───────────
  1. transform nằm trên CHÍNH thẻ <path>, không phải <g> bao ngoài.
  2. đường cong vẽ bằng BEZIER (có 'C'); lọc bỏ 'C' là bỏ luôn đường cong.
  3. glyph chữ cũng là <path> — phân biệt bằng fill="none" + stroke=.
  4. một <path> có thể chứa NHIỀU subpath ('M' lặp) = nhiều đường cong; nối lại
     thành một thì ra hình zigzag quét hết khung và bị loại sạch.
Thêm hai thứ chỉ thấy khi đo:
  · tiêu đề ô mang ký tự \x08 ở cuối ('AC20-D\x08') mà .strip() không bỏ được;
  · NÉT ĐỨT là DỮ LIỆU: chú giải cấp trang cho biết nét liền = áp vào 1,0 MPa,
    nét đứt = 0,7 MPa. Mỗi ô vẽ hai họ, và áp đặt 0,5 MPa có ở CẢ HAI.
"""
import re
import subprocess
import sys
from pathlib import Path

WORD = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
PATH_D = re.compile(r'<path[^>]*\sd="([^"]+)"')
NUM = re.compile(r"^-?\d+(?:\.\d+)?$")


def words(pdf, page):
    xml = subprocess.run(["pdftotext", "-bbox-layout", "-f", str(page), "-l", str(page),
                          str(pdf), "-"], capture_output=True, text=True).stdout
    # BỎ KÝ TỰ ĐIỀU KHIỂN: tiêu đề ô trong catalog AC mang \x08 (backspace) ở
    # cuối — 'AC20-D\x08'. .strip() không bỏ được, nên mọi regex mã hàng đều
    # trượt và 0/6 ô có tiêu đề. Chuẩn hoá ngay ở chỗ ĐỌC, không vá từng regex.
    out = []
    for a, b, c, d, t in WORD.findall(xml):
        t = "".join(ch for ch in t if ch.isprintable()).strip()
        if t:
            out.append((float(a), float(b), float(c), float(d), t))
    return out


def svg_paths(pdf, page):
    """Trả (đường_cong, đoạn_thẳng) ở TOẠ ĐỘ TRANG.

    đường_cong = [(điểm, nét_đứt)] · đoạn_thẳng = [(x0,y0,x1,y1, nét_đứt)]
    Đoạn thẳng dài ≥6 để bắt được cả VẠCH CHÚ GIẢI (dài ~21) chứ không chỉ khung.

    BỐN LỚP phải bóc, mỗi lớp tôi đều đoán sai một lần trước khi đo:
      1. transform nằm trên CHÍNH THẺ <path>, không phải <g> bao ngoài.
      2. đường cong vẽ bằng BEZIER (có 'C'), không phải polyline. Lọc bỏ 'C' là
         bỏ luôn đường cong — chỉ còn đường lưới.
      3. glyph chữ cũng là <path> — phân biệt bằng fill="none" + stroke= (đường
         vẽ) so với fill (chữ).
      4. đường lưới/khung là stroke nhưng THẲNG (một chiều gần như không đổi).

    Lấy điểm neo của bezier (điểm cuối mỗi đoạn C) chứ không lấy điểm điều khiển:
    điểm điều khiển KHÔNG nằm trên đường cong.
    """
    out = subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page),
                          str(pdf), "-"], capture_output=True, text=True).stdout
    MAT = re.compile(r'transform="matrix\(([^)]*)\)"')
    DD = re.compile(r'\sd="([^"]+)"')
    curves, lines = [], []
    # NÉT ĐỨT LÀ DỮ LIỆU, không phải trang trí: trang 22 có chú giải cấp trang
    # "Inlet pressure: 1.0 MPa" (nét liền) và "0.7 MPa" (nét đứt). Mỗi ô vẽ HAI
    # HỌ đường theo áp vào, nên áp đặt 0,5 xuất hiện ở CẢ HAI. Không phân biệt
    # thì hai điều kiện khác nhau bị gộp một nhãn và tra ra số của điều kiện
    # nào là ngẫu nhiên.
    for m in re.finditer(r'<path\b[^>]*>', out):
        tag = m.group(0)
        if 'fill="none"' not in tag or "stroke=" not in tag:
            continue                          # chữ, không phải đường vẽ
        md = DD.search(tag)
        if not md:
            continue
        d = md.group(1)
        # TÁCH THEO SUBPATH: mỗi 'M' mở một đường MỚI. Một thẻ <path> có thể chứa
        # cả 9 đường cong của một ô (đo được: trang 103 ô AR20 có đúng vậy). Nối
        # chúng lại thành một đường thì ra hình zigzag quét hết khung → bị loại
        # "ngoài khung", và ô đó mất sạch dữ liệu.
        subs, pts = [], []
        for seg in re.finditer(r"([MLC])((?:\s*-?[\d.]+){2,6})", d):
            op = seg.group(1)
            nums = [float(x) for x in re.findall(r"-?[\d.]+", seg.group(2))]
            if op == "M":
                if pts:
                    subs.append(pts)
                pts = []
            if op == "C" and len(nums) >= 6 and pts:
                # LẤY MẪU BEZIER, không chỉ lấy điểm neo. Bản trước chỉ giữ neo
                # cuối mỗi đoạn C nên hình dạng giữa hai neo bị thay bằng đoạn
                # thẳng — và nếu cả đường chỉ vẽ bằng MỘT đoạn C thì còn đúng 2
                # điểm, bị ngưỡng ≥3 loại sạch (đo được: 9/18 đường của trang 92
                # mất theo cách đó). Điểm điều khiển KHÔNG nằm trên đường cong nên
                # không dùng trực tiếp; phải nội suy bậc ba.
                x0, y0 = pts[-1]
                x1, y1, x2, y2, x3, y3 = nums[:6]
                for k in (1, 2, 3, 4):
                    t = k / 4.0
                    u = 1.0 - t
                    pts.append((u**3 * x0 + 3 * u * u * t * x1
                                + 3 * u * t * t * x2 + t**3 * x3,
                                u**3 * y0 + 3 * u * u * t * y1
                                + 3 * u * t * t * y2 + t**3 * y3))
            elif len(nums) >= 2:
                pts.append((nums[0], nums[1]))
        if pts:
            subs.append(pts)
        dash = "dasharray" in tag
        mm = MAT.search(tag)
        mat = None
        if mm:
            v = [float(x) for x in re.split(r"[ ,]+", mm.group(1).strip())]
            if len(v) == 6:
                mat = v
        for pts in subs:
            # THỨ TỰ QUAN TRỌNG: kiểm THẲNG trước, kiểm số điểm sau. Khung trục là
            # subpath 2 điểm (M…L…) nên lọc `len(pts) < 5` trước là bỏ mất khung —
            # đo được: 0 đoạn thẳng trên cả 3 trang, tức mất sạch mốc neo.
            if len(pts) < 2:
                continue
            if mat:
                a, b, c, dd_, e, f = mat
                pts = [(a * x + c * y + e, b * x + dd_ * y + f) for x, y in pts]
            xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
            dx, dy = max(xs) - min(xs), max(ys) - min(ys)
            if dx < 3 or dy < 3:
                # ≥6 để bắt cả VẠCH CHÚ GIẢI (dài ~21), không chỉ khung trục.
                if max(dx, dy) >= 6:
                    lines.append((min(xs), min(ys), max(xs), max(ys), dash))
                continue
            # ≥3 điểm: sau khi tách subpath, một đường cong có thể chỉ còn 3–4
            # đỉnh (catalog vẽ vài đoạn thẳng nối). Ngưỡng 5 làm mất sạch đường
            # cong của 3 ô đầu trang 103.
            if len(pts) >= 3:
                curves.append((pts, dash))
    return curves, lines


def _ticks(ws, axis, box):
    """Nhãn số trên một trục, trong vùng box=(x0,y0,x1,y1). Trả [(toạ_độ, giá_trị)]."""
    x0, y0, x1, y1 = box
    out = []
    for wx0, wy0, wx1, wy1, t in ws:
        if not NUM.match(t):
            continue
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            continue
        out.append((cx if axis == "x" else cy, float(t)))
    # gộp nhãn trùng vị trí (pdftotext đôi khi tách chữ số)
    out.sort()
    ded = []
    for pos, val in out:
        if ded and abs(ded[-1][0] - pos) < 1.5 and ded[-1][1] == val:
            continue
        ded.append((pos, val))
    return ded


def _fit(ticks):
    """Hồi quy tuyến tính pos→val. Trả (a, b) sao cho val = a*pos + b, hoặc None.

    Yêu cầu ≥3 nhãn và sai số nhỏ: trục log hoặc nhãn đọc lẫn sẽ cho sai số lớn
    → trả None để KHÔNG số hoá sai còn hơn số hoá bừa.
    """
    if len(ticks) < 3:
        return None
    n = len(ticks)
    sx = sum(p for p, _ in ticks); sy = sum(v for _, v in ticks)
    sxx = sum(p * p for p, _ in ticks); sxy = sum(p * v for p, v in ticks)
    den = n * sxx - sx * sx
    if abs(den) < 1e-9:
        return None
    a = (n * sxy - sx * sy) / den
    b = (sy - a * sx) / n
    span = max(v for _, v in ticks) - min(v for _, v in ticks) or 1.0
    err = max(abs(a * p + b - v) for p, v in ticks) / span
    return (a, b) if err < 0.04 else None


def _axis_caption(ws, box, axis):
    """Chú thích trục, ĐỌC TỪ TEXT. Trả chuỗi đã ghép, hoặc "".

    Không dùng offset cứng: lấy DẢI sát trục (dưới ô cho trục X, trái ô cho trục
    Y) rồi bỏ mọi từ là SỐ — số là vạch chia, chữ còn lại chính là chú thích. Vì
    vậy nó chạy trên mọi trang, không canh theo một trang.

    Đo được: tr22 X="Flow rate [L/min (ANR)]" · tr23 X="Inlet pressure [MPa]" ·
    tr92 Y="Pressure drop [MPa]". Ba chuỗi đó phân biệt đủ ba HỌ đồ thị.
    """
    x0, y0, x1, y1 = box[:4]
    sel = []
    for wx0, wy0, wx1, wy1, t in ws:
        if NUM.match(t):
            continue                       # vạch chia, không phải chú thích
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        if axis == "x" and x0 - 10 <= cx <= x1 + 10 and y1 + 1 <= cy <= y1 + 44:
            sel.append((cy, cx, t))
        elif axis == "y" and x0 - 92 <= cx <= x0 - 1 and y0 - 10 <= cy <= y1 + 10:
            sel.append((cx, cy, t))
    return " ".join(t for _, _, t in sorted(sel))


# ── HỌ ĐỒ THỊ ───────────────────────────────────────────────────────────────
# Catalog FRL có BA họ khác nhau, và trộn chúng là sai nghiêm trọng nhất có thể:
# trang 23 cho "6/6 ô đạt" nhưng trục X là ÁP VÀO [MPa] — ghi ra YAML thì áp
# suất bị engine đọc thành lưu lượng. Phân loại bằng CHÚ THÍCH TRỤC (text), là
# nguồn độc lập với việc trích đường cong.
#
#   flow_outlet   lưu lượng → áp ra      bộ điều áp AC/AR   giảm dần từ áp đặt
#   flow_drop     lưu lượng → sụt áp     lọc AFM/AFD/AFF    tăng dần từ 0
#   pressure_char áp vào   → áp ra       "Pressure Char."   tăng dần
def _single_inlet(ws):
    """Áp vào DUY NHẤT ghi bằng chữ trên trang, ví dụ 'Condition: Inlet pressure
    of 0.7 MPa'. Trả float, hoặc None nếu không có/không rõ.

    Có trang chỉ vẽ MỘT điều kiện áp vào nên không cần chú giải nét — es40-70-ARG-B
    tr4 và ES40-60-AR10-A tr2. Câu điều kiện là text nên vẫn là nguồn ĐỘC LẬP với
    việc trích đường cong. Nhiều giá trị khác nhau thì TRẢ None: thà báo không
    biết hơn là chọn một cái.
    """
    rows = {}
    for wx0, wy0, wx1, wy1, t in ws:
        rows.setdefault(round((wy0 + wy1) / 2 / 2.5), []).append(((wx0 + wx1) / 2, t))
    vals = set()
    for _, items in rows.items():
        line = " ".join(t for _, t in sorted(items))
        for m in re.finditer(r"(?i)inlet\s+pressure\s+of\s+([\d.]+)\s*MPa", line):
            try:
                vals.add(float(m.group(1)))
            except ValueError:
                pass
    return vals.pop() if len(vals) == 1 else None


def _kind(x_cap, y_cap):
    x, y = x_cap.lower(), y_cap.lower()
    x_flow = "l/min" in x or "m3/min" in x or "dm3" in x
    if x_flow and "drop" in y:
        return "flow_drop"
    if x_flow and "outlet" in y:
        return "flow_outlet"
    if "inlet pressure" in x and "outlet" in y:
        return "pressure_char"
    return None



def _legend(ws, lines):
    """Chú giải cấp trang: nét liền/nét đứt ↔ ÁP VÀO [MPa]. Trả {dash: mpa} | None.

    Trang 22/103/128 có hai dòng "Inlet pressure: 1.0 MPa" / "0.7 MPa", mỗi dòng
    kèm một vạch mẫu bên trái. Mỗi ô vẽ HAI HỌ đường theo áp vào đó, và áp đặt
    0,5 MPa xuất hiện ở CẢ HAI họ — gộp lại thì tra ra số của điều kiện nào là
    ngẫu nhiên.

    GHÉP THEO THỨ TỰ ĐỌC, không theo khoảng cách cy. Đo được: vạch ở cy 85,3 và
    93,1; chữ ở cy 81 và 89. Ghép theo cy gần nhất thì 85,3 → 89 (Δ3,7 < 4,3) là
    NGƯỢC. Chú giải là danh sách dọc nên thứ tự mới là quan hệ đúng.

    Kết quả còn được KIỂM CHỨNG BẰNG VẬT LÝ ở digitize(): họ nào chứa áp đặt cao
    nhất phải là họ có áp vào cao hơn — không điều áp lên được.
    """
    # ── TÌM VẠCH MẪU TRƯỚC, RỒI MỚI TÌM DÒNG CHỮ ────────────────────────────
    # Bản trước lấy MỌI từ 'Inlet' trên trang rồi đòi số vạch = số dòng. Trang
    # es40-72-AR_M-D tr11 có thêm hai ghi chú 'Inlet pressure' NGAY TRONG ô (cy
    # 456 và 623) nên 2 vạch ≠ 4 dòng và cả trang bị bỏ. Vạch mẫu là thứ đặc
    # trưng của chú giải, nên nó phải là mốc.
    marks = []
    for lx0, ly0, lx1, ly1, dash in lines:
        if (ly1 - ly0) >= 3 or not (6 <= lx1 - lx0 <= 40):
            continue
        marks.append(((ly0 + ly1) / 2, lx1, dash))
    if len(marks) < 2:
        return None
    marks.sort()
    m_lo, m_hi = marks[0][0], marks[-1][0]
    m_right = max(m[1] for m in marks)

    rows = []
    for wx0, wy0, wx1, wy1, t in ws:
        if not t.lower().startswith("inlet"):
            continue
        cy, cx = (wy0 + wy1) / 2, (wx0 + wx1) / 2
        if not (m_lo - 12 <= cy <= m_hi + 12 and cx >= m_right - 4):
            continue                      # ghi chú ở nơi khác, không phải chú giải
        vals = [float(u) for ux0, uy0, ux1, uy1, u in ws
                if NUM.match(u) and abs((uy0 + uy1) / 2 - cy) <= 2.0
                and (ux0 + ux1) / 2 > cx]
        if vals:
            rows.append((cy, cx, max(vals)))
    if len(rows) < 2:
        return None
    rows.sort()
    marks = [m for m in marks if m_lo - 12 <= m[0] <= m_hi + 12]
    marks = [(m[0], m[2]) for m in marks]
    if len(marks) != len(rows):
        return None
    out = {}
    for (_, dash), (_, _, mpa) in zip(marks, rows):
        if dash in out and out[dash] != mpa:
            return None                       # hai vạch cùng kiểu nét → không phân biệt được
        out[dash] = mpa
    return out if len(out) == 2 else None


def _axes(ws):
    """Tìm các Ô ĐỒ THỊ từ NHÃN TRỤC. Trả [{"yc","xr",...}].

    ĐÂY LÀ THAY ĐỔI THIẾT KẾ, không phải tinh chỉnh. Bản trước suy ô từ CỤM
    ĐƯỜNG CONG rồi cộng offset để tìm nhãn. Hệ quả: mỗi lần sửa bộ lọc đường
    cong là bbox đổi → mọi vùng nhãn lệch → cả trang mất nhãn. Đã xảy ra BA lần
    (lọc lưới, tách subpath, hạ ngưỡng số điểm). Vòng lặp đó không hội tụ.

    Nhãn trục thì KHÁC: nó là text với toạ độ, do catalog đặt, KHÔNG phụ thuộc
    cách tôi trích đường cong. Và nó chính là mốc hiệu chuẩn. Nên hãy để nó
    định nghĩa ô luôn:

        cột ≥3 số cùng cx, giá trị giảm khi cy tăng   →  trục Y
        hàng ≥3 số cùng cy, giá trị tăng khi cx tăng  →  trục X
        ghép cột Y với hàng X ngay bên dưới nó        →  một ô

    Đường cong sau đó được GÁN vào ô theo vị trí, không ngược lại.
    """
    # Mỗi nhãn số: (tâm_x, tâm_y, giá_trị, mép_phải).
    # MÉP PHẢI cần cho trục Y: nhãn trục Y CANH PHẢI theo trục nên mép phải bằng
    # nhau còn tâm thì lệch theo số chữ số — đo trên tr22: '0.8'…'0.1' có tâm
    # 69,7 nhưng '0' có tâm 72,2, mép phải cả hai đều 73,9. Gộp theo tâm với dung
    # sai 3px thì trang tr92 (nhãn 0,02/0,01/0) bị tách cột và mất sạch 6 ô.
    nums = [((wx0 + wx1) / 2, (wy0 + wy1) / 2, float(t), wx1)
            for wx0, wy0, wx1, wy1, t in ws if NUM.match(t)]

    def group(items, key, tol=3.0):
        out = []
        for it in sorted(items, key=key):
            if out and abs(key(it) - key(out[-1][-1])) <= tol:
                out[-1].append(it)
            else:
                out.append([it])
        return out

    def runs(g, pos, rising):
        """Cắt một cột/hàng nhãn thành từng TRỤC riêng.

        Cần bước này vì nhãn Y của CẢ BA HÀNG ô trên trang dùng chung cx (đo
        được: cx≈70, 27 nhãn = 9 giá trị × 3 ô). Gộp theo cx rồi đòi đơn điệu
        thì cả nhóm bị loại. Mỗi ô mới bắt đầu lại từ 0,8 nên chỗ giá trị ĐẢO
        CHIỀU chính là ranh giới giữa hai ô.
        """
        g = sorted(g, key=pos)
        out, cur = [], []
        for it in g:
            broke = cur and ((it[2] > cur[-1][2] + 1e-9) if not rising
                             else (it[2] < cur[-1][2] - 1e-9))
            if broke:
                out.append(cur)
                cur = []
            cur.append(it)
        if cur:
            out.append(cur)
        return [r for r in out if len({p[2] for p in r}) >= 3]

    ycols, xrows = [], []
    for g in group(nums, lambda p: p[3]):                  # trục Y: gộp theo MÉP PHẢI
        ycols += runs(g, lambda p: p[1], rising=False)     # và GIẢM xuống dưới
    for g in group(nums, lambda p: p[1]):                  # trục X: gộp theo hàng
        xrows += runs(g, lambda p: p[0], rising=True)      # và TĂNG sang phải

    panels = []
    for yc in ycols:
        xc, ytop, ybot = max(p[3] for p in yc), yc[0][1], yc[-1][1]
        best = None
        for xr in xrows:
            cy = xr[0][1]
            if not (ybot - 6 <= cy <= ybot + 30):
                continue                                    # phải nằm ngay DƯỚI cột Y
            if not (xc - 8 <= xr[0][0] <= xc + 44):
                continue                                    # và bắt đầu ngay PHẢI cột Y
            if best is None or cy < best[0][1]:
                best = xr
        if best is None:
            continue
        panels.append({"yc": yc, "xr": best,
                       "L": best[0][0], "R": best[-1][0],
                       "T": ytop, "B": ybot, "xc": xc})
    panels.sort(key=lambda p: (round(p["T"] / 20), p["L"]))
    return panels


def _cluster(curves, gap=12.0):
    """Gom đường cong thành Ô ĐỒ THỊ theo khoảng cách. Trả [[curve,…],…].

    Một trang catalog có 4–6 ô. Không gom thì nhãn trục của ô này bị áp cho đường
    cong của ô kia — sai model, sai số liệu, mà không có dấu hiệu gì để phát hiện.

    gap ĐO ĐƯỢC, không đoán: trên trang 22 của catalog AC, gap ≤ 20 cho đúng 6 ô,
    gap = 30 gộp hết thành 1. Chọn 12 để có biên an toàn hai phía.
    """
    boxes = []
    for q in curves:
        xs = [p[0] for p in q]; ys = [p[1] for p in q]
        boxes.append([min(xs), min(ys), max(xs), max(ys), [q]])
    changed = True
    while changed:
        changed = False
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                A, B = boxes[a], boxes[b]
                if (A[0] - gap <= B[2] and B[0] - gap <= A[2]
                        and A[1] - gap <= B[3] and B[1] - gap <= A[3]):
                    A[0] = min(A[0], B[0]); A[1] = min(A[1], B[1])
                    A[2] = max(A[2], B[2]); A[3] = max(A[3], B[3])
                    A[4] += B[4]
                    boxes.pop(b); changed = True
                    break
            if changed:
                break
    return boxes


def _frame(lines, box):
    """Hình chữ nhật VÙNG VẼ quanh một cụm đường cong, dựng từ khung trục.

    ĐÂY LÀ MỐC NEO. Trước đây tôi lấy bbox đường cong rồi cộng offset đo trên
    ĐÚNG MỘT trang (nhãn Y ở x0+30, nhãn X ở y1-18…). Đổi bộ lọc đường cong một
    chút là bbox đổi, mọi offset lệch, cả trang mất nhãn — đã xảy ra hai lần.
    Khung trục thì do catalog vẽ, không đổi theo cách tôi trích đường cong.

    Cạnh trái/phải = đoạn ĐỨNG gần nhất hai bên cụm, có tầm dọc phủ cụm.
    Cạnh trên/dưới = đoạn NGANG gần nhất trên/dưới, có tầm ngang phủ cụm.
    Thiếu cạnh nào thì lùi về bbox cụm cho cạnh đó — không bịa.
    """
    cx0, cy0, cx1, cy1 = box[:4]
    L = R = T = B = None
    for lx0, ly0, lx1, ly1 in lines:
        vert = (lx1 - lx0) < 3
        if vert and min(ly1, cy1) - max(ly0, cy0) > (cy1 - cy0) * 0.5:
            x = (lx0 + lx1) / 2
            if x <= cx0 + 2 and (L is None or x > L):
                L = x
            elif x >= cx1 - 2 and (R is None or x < R):
                R = x
        elif not vert and min(lx1, cx1) - max(lx0, cx0) > (cx1 - cx0) * 0.5:
            y = (ly0 + ly1) / 2
            if y <= cy0 + 2 and (T is None or y > T):
                T = y
            elif y >= cy1 - 2 and (B is None or y < B):
                B = y
    return (L if L is not None else cx0, T if T is not None else cy0,
            R if R is not None else cx1, B if B is not None else cy1)


def _title_for(ws, box, used=()):
    """Tiêu đề ô = mã hàng gần nhất PHÍA TRÊN ô đó, MỖI TIÊU ĐỀ DÙNG MỘT LẦN.

    Không loại tiêu đề đã dùng thì mọi ô cùng nhận một tên: trang 22 gán "AC60-D"
    cho ô có trục tới 2000 L/min (thực ra là AC20-D). Sai tên model = sai toàn bộ
    ý nghĩa số liệu.
    """
    x0, y0, x1, y1 = box[:4]
    best, bd = None, 1e9
    for wx0, wy0, wx1, wy1, t in ws:
        if t in used:
            continue
        # NGOẶC LÀ HỢP LỆ: catalog ghi 'AR20(K)-D' nghĩa là ô này dùng cho CẢ
        # AR20-D và AR20K-D. Regex cũ loại ngoặc nên trang 103/128 mất hết tiêu
        # đề (0/6, 0/5) — số liệu không gắn được vào model nào là vô dụng.
        if not re.match(r"^[A-Z]{1,4}\d{2,4}[A-Z0-9()/\-]*$", t) or len(t) < 4:
            continue
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        # Tiêu đề nằm ngay TRÊN cạnh trên của khung. Cho phép tới y0-90 (bản
        # trước) là bắt luôn tiêu đề TRANG ở cy=34 — ô đầu nhận "AC60-D" trong
        # khi trục chỉ tới 2000 L/min (đúng ra AC20-D).
        # ĐO: tiêu đề ô ở cy = T-23 (nhãn Y trên cùng ở T=135.9, tiêu đề ở 112.9).
        # Băng tới T-40 vẫn KHÔNG bắt được tiêu đề TRANG (cy≈34 = T-102).
        if not (y0 - 40 <= cy <= y0 + 2):
            continue
        if not (x0 - 46 <= cx <= x0 + 70):
            continue
        d = abs(y0 - 23 - cy) + abs(cx - x0) * 0.5
        if d < bd:
            best, bd = t, d
    return best


def interp(pts, x):
    """Nội suy tuyến tính, KHÔNG ngoại suy. Trả None nếu x ngoài dải."""
    if not pts or x < pts[0][0] or x > pts[-1][0]:
        return None
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if x1 <= x <= x2:
            return y1 if x2 == x1 else y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    return None


def envelope(curves, thin=0.001):
    """Đường bao TRÊN của nhiều đường sụt áp. Trả [[x, y]…].

    DÙNG KHI KHÔNG ĐỌC ĐƯỢC NHÃN: mỗi ô sụt áp vẽ 5 đường (tr92: 3) ứng với các
    áp vào P1 khác nhau, nhưng nhãn P1 là text XOAY mà pdftotext tách thành ký tự
    rời — không đọc lại được cho chắc. Bao trên bảo thủ đúng hướng: thừa sụt áp
    thì engine chọn cỡ TO hơn, không nhỏ hơn.

    CẮT TẠI x_common — chỗ MỌI đường còn định nghĩa. Ngoài đó, "max" chỉ còn là
    max của MỘT SỐ điều kiện, nên nó GIẢM khi lưu lượng tăng: đo được AF20-D đi
    từ 0,1 MPa ở 736 L/min xuống 0,079 ở 1500 L/min. Sụt áp giảm khi lưu lượng
    tăng là vô nghĩa vật lý, và số đó vào engine thì ước THẤP hơn thực tế — sai
    theo hướng nguy hiểm. Ngoài x_common là gap, không phải số.

    ĐÂY LÀ HÀM DUY NHẤT tính bao trên: cả bộ sinh YAML và cổng kiểm đều gọi nó.
    Nhân bản hai bản thì cổng kiểm một thứ mà YAML ghi thứ khác.
    """
    if not curves:
        return []
    x_common = min(max(x for x, _ in c) for c in curves)
    xs = sorted({round(x, 1) for c in curves for x, _ in c if x <= x_common})
    out = []
    run = 0.0
    for x in xs:
        ys = [v for c in curves for v in [interp(c, x)] if v is not None]
        if not ys:
            continue
        run = max(run, max(ys))          # max lũy tiến: nhiễu không được làm giảm
        out.append([x, round(run, 4)])
    if not out:
        return []
    keep = [out[0]]
    for q in out[1:-1]:
        if q[1] - keep[-1][1] >= thin:
            keep.append(q)
    if len(out) > 1:
        keep.append(out[-1])
    return keep


def digitize(pdf, page, samples=10):
    """Trích MỌI ô đồ thị trên một trang, mỗi ô hiệu chuẩn riêng.

    Ô do NHÃN TRỤC định nghĩa (_axes), đường cong được GÁN vào ô theo vị trí.
    Chiều đó quan trọng: nhãn trục không phụ thuộc bộ lọc đường cong, nên sửa
    phần trích đường cong không còn làm lệch vùng nhãn.
    """
    ws = words(pdf, page)
    curves, lines = svg_paths(pdf, page)
    legend = _legend(ws, lines)
    if legend is None:
        # Không có chú giải nét → có thể trang chỉ vẽ MỘT điều kiện áp vào, ghi
        # bằng chữ. Cả hai kiểu nét khi đó cùng một áp vào.
        one = _single_inlet(ws)
        if one is not None:
            legend = {True: one, False: one}
    if not ws:
        return {"ok": False, "error": "trang không có text — có thể là ảnh scan"}
    if not curves:
        return {"ok": False, "error": "không thấy đường cong vector — có thể là ảnh raster"}

    panels, used_titles = [], set()
    for ax in _axes(ws):
        L, T, R, B = ax["L"], ax["T"], ax["R"], ax["B"]
        yt = [(cy, v) for _, cy, v, _ in ax["yc"]]
        yt_vals = [v for _, v in yt]
        xt = [(cx, v) for cx, _, v, _ in ax["xr"]]
        fx, fy = _fit(xt), _fit(yt)
        x_cap = _axis_caption(ws, (L, T, R, B), "x")
        y_cap = _axis_caption(ws, (ax["xc"], T, R, B), "y")
        kind = _kind(x_cap, y_cap)
        title = _title_for(ws, (L, T, R, B), used_titles)
        if title:
            used_titles.add(title)
        pan = {"title": title, "box": [round(v, 1) for v in (L, T, R, B)],
               "kind": kind,
               "x_ticks": [v for _, v in xt], "y_ticks": [v for _, v in yt],
               "x_caption": x_cap, "y_caption": y_cap, "series": []}
        if not fx or not fy:
            pan["error"] = (f"chưa hiệu chuẩn được trục (X:{len(xt)} nhãn, "
                            f"Y:{len(yt)} nhãn — cần ≥3 mỗi trục, thẳng hàng)")
            panels.append(pan)
            continue
        if kind not in ("flow_outlet", "flow_drop"):
            # KHÔNG số hoá họ chưa có ground truth. Trang 23 từng báo "6/6 ô đạt"
            # trong khi trục X là ÁP VÀO [MPa] — ghi ra YAML là engine đọc áp
            # suất thành lưu lượng. Từ chối thì an toàn; lọc bằng luật tự nghĩ
            # mà không kiểm chứng được thì không.
            pan["error"] = (f"họ đồ thị '{kind or 'không nhận dạng được'}' chưa có "
                            "ground truth — chỉ số hoá lưu lượng→áp ra và "
                            "lưu lượng→sụt áp")
            panels.append(pan)
            continue

        # GÁN đường cong vào ô: ≥80% điểm nằm trong khung. Không dùng bao đường
        # cong để suy ra ô nữa — chiều phụ thuộc đã đảo.
        # ── GÁN ĐƯỜNG VÀO Ô THEO ĐIỂM ĐẦU ───────────────────────────────────
        # Mọi đường đặc trưng đều BẮT ĐẦU ở trục trái của ô nó (lưu lượng 0), nên
        # điểm đầu chỉ đúng một ô — các ô không chồng nhau theo cả hai chiều.
        # Luật cũ "≥80% điểm trong khung" bỏ mất cả họ áp vào 1,0 MPa của ô
        # AR40(K)-06-D: vùng vẽ ô đó rộng tới x=689 còn nhãn cuối ở 544, nên
        # đường chỉ có ~70% điểm trong dải nhãn và bị loại IM LẶNG.
        qs = []
        for q, dash in curves:
            x0q, y0q = min(q)
            if not (L - 6 <= x0q <= L + 0.2 * (R - L)
                    and T - 6 <= y0q <= B + 6):
                continue
            inside = sum(1 for x, y in q
                         if L - 6 <= x <= R + 6 and T - 6 <= y <= B + 6)
            if inside >= 0.4 * len(q):
                qs.append((q, dash))
        pan["n_curves"] = len(qs)

        ax_, bx = fx; ay, by = fy
        xlo, xhi = min(v for _, v in xt), max(v for _, v in xt)
        ylo, yhi = min(v for _, v in yt), max(v for _, v in yt)
        xspan = (xhi - xlo) or 1.0
        yspan = (yhi - ylo) or 1.0
        tol = 0.02 * yspan / 0.8 if yspan < 0.8 else 0.02
        dropped = []
        trimmed = [0]
        for q, dash in sorted(qs, key=lambda t: len(t[0]), reverse=True):
            pts = sorted(q)
            step = max(1, len(pts) // samples)
            data = [[round(ax_ * px + bx, 1), round(ay * py + by, 3)]
                    for px, py in pts[::step]]
            if len(data) < 3:
                continue
            # ── LỌC BẰNG TÍNH CHẤT VẬT LÝ ────────────────────────────────────
            # Không lọc bằng ước lượng hình học. Các tính chất dưới đây suy từ Ý
            # NGHĨA đồ thị, còn nhãn trục là nguồn ĐỘC LẬP với đường cong. Khung
            # vẽ và vạch lưới vi phạm ít nhất một tính chất nên bị loại.
            # ── CẮT PHẦN NGOÀI DẢI NHÃN, không loại cả đường ─────────────────
            # Đo được: ô AC40-06-D/AR40-06-D có vùng vẽ rộng tới ~8600 L/min
            # trong khi nhãn cuối là 7000. Loại cả đường thì hai ô đó MẤT SẠCH
            # họ áp vào 1,0 MPa mà không có dấu hiệu gì — im lặng thiếu dữ liệu
            # còn tệ hơn báo thiếu.
            # Ngoài dải nhãn là NGOẠI SUY trục, nên không giữ. Trong dải thì kẹp
            # phần tràn nhỏ của nét vẽ (≤1,09%, xem ground truth).
            # An toàn: khung và lưới là đường THẲNG, đã tách sang `lines` từ
            # svg_paths, không bao giờ tới đây — nên cắt không mở cửa cho chúng.
            tolx = 0.02 * xspan
            kept, cut = [], 0
            for x, y in data:
                if (x < xlo - tolx or x > xhi + tolx
                        or y < ylo - tol or y > yhi + tol):
                    cut += 1
                    continue
                kept.append([round(min(max(x, xlo), xhi), 1),
                             round(min(max(y, ylo), yhi), 3)])
            over_x = max([(xlo - x) / xspan for x, _ in data]
                         + [(x - xhi) / xspan for x, _ in data] + [0.0])
            over_y = max([ylo - y for _, y in data]
                         + [y - yhi for _, y in data] + [0.0])
            # Báo mức tràn THẬT, không cắt về dung sai. Cắt là tự làm mình luôn
            # đúng. Con số này chỉ để CHẨN ĐOÁN — phép kiểm hiệu chuẩn thật là
            # C3 (nhãn x_max) và C4 (mọi đường bắt đầu đúng nhãn Y).
            pan["overshoot_x_frac"] = max(pan.get("overshoot_x_frac", 0.0), over_x)
            pan["overshoot_y_mpa"] = max(pan.get("overshoot_y_mpa", 0.0), over_y)
            if len(kept) < 3:
                dropped.append("ngoài khung")
                continue
            if cut:
                trimmed[0] += cut
            data = kept
            if kind == "flow_drop":
                # SỤT ÁP: tăng theo lưu lượng, và BẰNG 0 khi lưu lượng bằng 0.
                # Mốc neo (0,0) là vật lý — không lọc gì thì khung và vạch lưới
                # lọt vào, mà ở đây engine lấy ĐƯỜNG BAO TRÊN nên một đường lạ
                # nằm trên là làm sai toàn bộ.
                if any(y1 - y2 > tol for (_, y1), (_, y2) in zip(data, data[1:])):
                    dropped.append("sụt áp giảm khi lưu lượng tăng")
                    continue
                if (data[0][0] > xlo + 0.02 * xspan
                        or data[0][1] > ylo + 0.05 * yspan):
                    dropped.append("điểm đầu không ở gốc (0 lưu lượng, 0 sụt áp)")
                    continue
            else:
                # áp ra KHÔNG tăng khi lưu lượng tăng
                if any(y2 - y1 > tol for (_, y1), (_, y2) in zip(data, data[1:])):
                    dropped.append("áp ra tăng")
                    continue
                # mỗi đường BẮT ĐẦU đúng áp đặt của nó — tức một nhãn trục Y
                if not any(abs(data[0][1] - v) <= 0.025 for _, v in yt):
                    dropped.append("điểm đầu không trùng nhãn Y")
                    continue
            # ÁP VÀO của đường này, đọc từ chú giải cấp trang qua kiểu nét.
            # Thiếu chú giải thì KHÔNG gán bừa: để None và báo, vì hai họ đường
            # cùng nhãn áp đặt mà không phân biệt được thì số vô nghĩa.
            pan["series"].append({"inlet_mpa": (legend or {}).get(dash),
                                  "dashed": dash, "points": data})
        pan["dropped"] = dropped
        pan["trimmed_points"] = trimmed[0]
        if kind == "flow_drop":
            # KHÔNG GÁN NHÃN CHO HỌ NÀY. Nhãn mỗi đường là áp vào P1, viết XOAY
            # bên trong ô, và pdftotext tách nó thành ký tự rời ('P','1','=','0',
            # '.3','MP','a') — không có nguồn text nào đọc lại được cho chắc. Nên
            # để nhãn None và nói rõ; bên ghi YAML sẽ lấy ĐƯỜNG BAO TRÊN (sụt áp
            # lớn nhất), bảo thủ đúng hướng: thừa sụt áp thì chọn cỡ to hơn.
            pan["unlabelled"] = True
            panels.append(pan)
            continue
        if legend is None and pan["series"]:
            pan["error"] = ("trang có HAI họ đường theo áp vào nhưng không đọc "
                            "được chú giải → không phân biệt được, bỏ toàn bộ ô")
            pan["series"] = []
        else:
            # KIỂM CHỨNG VẬT LÝ phép ghép nét↔áp vào: không điều áp LÊN được, nên
            # áp đặt của mỗi đường phải < áp vào của họ nó. Ghép ngược là vi phạm
            # hàng loạt. Đây là kiểm độc lập với thứ tự đọc chú giải.
            bad = []
            for sr in pan["series"]:
                setp = min(yt_vals, key=lambda v: abs(v - sr["points"][0][1]))
                if sr["inlet_mpa"] is not None and setp > sr["inlet_mpa"] + 1e-9:
                    bad.append((setp, sr["inlet_mpa"]))
            if bad:
                pan["error"] = (f"ghép kiểu nét ↔ áp vào SAI: {len(bad)} đường có "
                                f"áp đặt > áp vào (ví dụ {bad[0][0]} > {bad[0][1]}) "
                                "— không điều áp lên được")
                pan["series"] = []
        panels.append(pan)

    good = [p for p in panels if p.get("series")]
    kinds = [p["kind"] for p in panels if p.get("kind")]
    # `kind` chỉ đặt khi TOÀN TRANG một họ. Trước đây lấy họ ĐA SỐ, nhưng trang
    # es40-70-ARG-B tr4 và es40-72-AR_M-D tr11 trộn 3 ô lưu lượng→áp ra với 3 ô
    # áp vào→áp ra, nên "đa số" là một con số vô nghĩa và làm tiêu chí phân loại
    # báo sai. Trang trộn họ thì phải xét theo TỪNG Ô.
    return {"ok": bool(good), "page": page, "n_curves": len(curves),
            "kind": kinds[0] if kinds and len(set(kinds)) == 1 else None,
            "kinds": {k: kinds.count(k) for k in sorted(set(kinds))},
            "panels": panels, "n_ok": len(good),
            "error": None if good else "không ô nào hiệu chuẩn được"}


def scan(pdf):
    """Tìm trang có đồ thị: có polyline vector VÀ nhãn 'characteristic'."""
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    m = re.search(r"Pages:\s+(\d+)", info)
    n = int(m.group(1)) if m else 0
    hits = []
    for pg in range(1, n + 1):
        t = subprocess.run(["pdftotext", "-f", str(pg), "-l", str(pg), str(pdf), "-"],
                           capture_output=True, text=True).stdout
        if not re.search(r"(?i)characteristic", t):
            continue
        if re.search(r"p\.\s*\d", t[:500]):      # mục lục
            continue
        hits.append(pg)
    return hits


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "--scan":
        pdf = argv[1]
        pgs = scan(pdf)
        print(f"{Path(pdf).name}: {len(pgs)} trang có đồ thị → {pgs}")
        return 0
    pdf, page = argv[0], int(argv[1])
    r = digitize(pdf, page)
    if not r.get("ok"):
        print(f"✗ trang {page}: {r.get('error')}")
        for k in ("x_ticks", "y_ticks", "panels"):
            if r.get(k):
                print(f"    {k}: {r[k]}")
        return 1
    print(f"✓ trang {page}: {r['n_paths']} polyline · {len(r['series'])} đường trích được")
    print(f"    trục X: {r['x_unit']}  nhãn {[v for _, v in r['x_ticks']][:6]}")
    print(f"    trục Y: {r['y_unit']}  nhãn {[v for _, v in r['y_ticks']][:6]}")
    print(f"    ô đồ thị trên trang: {r['panels']}")
    for i, s in enumerate(r["series"], 1):
        print(f"    đường {i}: {s['n_points']} điểm gốc → {s['points'][:4]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
