"""Số hoá đồ thị catalog TỰ ĐỘNG từ vector trong PDF — không click tay.

VÌ SAO LÀM ĐƯỢC: đồ thị trong catalog SMC được vẽ bằng VECTOR, không phải ảnh
raster. `pdftocairo -svg` cho ra đường cong dưới dạng polyline `M x y L x y L…`,
còn `pdftotext -bbox-layout` cho nhãn trục kèm toạ độ. Có hai thứ đó là đủ:

    nhãn trục (text + toạ độ)  →  hiệu chuẩn pixel → giá trị thật
    polyline (toạ độ pixel)    →  áp hiệu chuẩn   → tập điểm dữ liệu

Spec §7 của prompt sơ đồ đề xuất công cụ click tay từng điểm. Cách này chính xác
hơn (không lệ thuộc tay người) và chạy được trên cả trăm đồ thị.

    python3 -m parsers.pdf_chart <pdf> <trang>            # xem trích được gì
    python3 -m parsers.pdf_chart <pdf> <trang> --yaml     # in ra YAML
    python3 -m parsers.pdf_chart --scan <pdf>             # tìm trang có đồ thị

TRẠNG THÁI ĐO ĐƯỢC (2026-08-24) — CHƯA DÙNG ĐƯỢC CHO ENGINE:

    catalog                          trang   ô đạt/tổng   có tiêu đề
    es40-69-AC-D.pdf                    22       6/6          0/6
    es40-69-AC-D.pdf                    61       0/1          0/1
    es40-72-AR_M-D.pdf                  20       0/0          0/0
    7-1-2-p0723-0963-SY3000_en.pdf      45       0/4          0/4
    ES13-12-VHS-D.pdf                    8       0/2          0/2

KỸ THUẬT ĐÚNG, IMPLEMENT CHƯA TỔNG QUÁT. Số liệu trích ra ở trang 22 hợp lý về
vật lý (áp ra 0,602 → 0,494 MPa khi lưu lượng 15 → 1012 L/min, đúng dạng đường
đặc trưng). Nhưng chỉ 1/5 trang chạy, vì vùng tìm nhãn trục đang HARDCODE theo số
đo của đúng trang đó:

    nhãn Y ở cx ≈ x0+30 ·  nhãn X ở cy ≈ y1-18 ·  tiêu đề ở cy ≈ y0-8

Đây đúng lớp lỗi đã phê phán ở prototype ("mainY=380 cứng"): canh theo một trang
thì trang khác lệch.

CÁCH SỬA ĐÚNG (chưa làm): hiện đang LOẠI các đường thẳng coi là "lưới", nhưng
chính chúng là KHUNG TRỤC. Dùng khung để xác định hình chữ nhật vùng vẽ, rồi tìm
nhãn ngay cạnh khung — không cần offset hardcode nào. Đó là mốc neo tự nhiên và
sẽ tổng quát.

CÒN THIẾU nữa: gán tiêu đề (0/6 ở trang chạy được) nên số liệu KHÔNG gắn được vào
model nào → chưa dùng được. Và không có nguồn đối chiếu độc lập cho đồ thị AC
(bảng số duy nhất trong catalog là dẫn nạp âm của VAN, đã số hoá ở
db/seed/charts/sy-flow.yaml). Sai cỡ FRL là sụt áp khi nhiều xy-lanh chạy — nên
KHÔNG ghi số ra YAML cho engine dùng khi chưa kiểm chứng được.

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
    return [(float(a), float(b), float(c), float(d), t.strip())
            for a, b, c, d, t in WORD.findall(xml) if t.strip()]


def svg_paths(pdf, page):
    """Đường cong đồ thị, đã đưa về TOẠ ĐỘ TRANG. Trả [(loại, [(x,y)…])].

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
    curves = []
    for m in re.finditer(r'<path\b[^>]*>', out):
        tag = m.group(0)
        if 'fill="none"' not in tag or "stroke=" not in tag:
            continue                          # chữ, không phải đường vẽ
        md = DD.search(tag)
        if not md:
            continue
        d = md.group(1)
        pts = []
        for seg in re.finditer(r"([MLC])((?:\s*-?[\d.]+){2,6})", d):
            nums = [float(x) for x in re.findall(r"-?[\d.]+", seg.group(2))]
            if seg.group(1) == "C" and len(nums) >= 6:
                pts.append((nums[4], nums[5]))     # điểm NEO, bỏ 2 điểm điều khiển
            elif len(nums) >= 2:
                pts.append((nums[0], nums[1]))
        if len(pts) < 5:
            continue
        mm = MAT.search(tag)
        if mm:
            v = [float(x) for x in re.split(r"[ ,]+", mm.group(1).strip())]
            if len(v) == 6:
                a, b, c, dd_, e, f = v
                pts = [(a * x + c * y + e, b * x + dd_ * y + f) for x, y in pts]
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        if (max(xs) - min(xs)) < 3 or (max(ys) - min(ys)) < 3:
            continue                          # đường lưới/khung, không phải đường cong
        curves.append(pts)
    return curves


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


def axis_label(ws, box, keys=("L/min", "MPa", "m3/min", "dm3")):
    """Nhãn đơn vị đọc được trong vùng — KHÔNG suy, không đoán."""
    x0, y0, x1, y1 = box
    for wx0, wy0, wx1, wy1, t in ws:
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1 and any(k in t for k in keys):
            return t
    return None


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
        if not re.match(r"^[A-Z]{1,4}\d{2,4}[A-Z0-9\-]*$", t) or len(t) < 4:
            continue
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        # ĐO trên trang 22: tiêu đề ô ở cy ≈ y0-8, cx ≈ x0+20.
        # Cho phép tới y0-90 (như bản trước) là bắt luôn tiêu đề TRANG ở cy=34 —
        # nên ô đầu nhận "AC60-D" trong khi trục chỉ tới 2000 L/min (đúng ra AC20-D).
        if not (y0 - 20 <= cy <= y0 + 4):
            continue
        if not (x0 - 10 <= cx <= x0 + 60):
            continue
        d = abs(y0 - 8 - cy) + abs(cx - (x0 + 20)) * 0.5
        if d < bd:
            best, bd = t, d
    return best


def digitize(pdf, page, samples=10):
    """Trích MỌI ô đồ thị trên một trang, mỗi ô hiệu chuẩn riêng."""
    ws = words(pdf, page)
    curves = svg_paths(pdf, page)
    if not ws:
        return {"ok": False, "error": "trang không có text — có thể là ảnh scan"}
    if not curves:
        return {"ok": False, "error": "không thấy đường cong vector — có thể là ảnh raster"}

    panels, used_titles = [], set()
    for box in sorted(_cluster(curves), key=lambda b: (b[1], b[0])):
        x0, y0, x1, y1, qs = box
        if (x1 - x0) < 60 or (y1 - y0) < 40:
            continue                                   # quá nhỏ, không phải ô đồ thị
        # Băng tìm nhãn phải NỚI RỘNG: hộp ô lấy từ bao đường cong nên nhãn trục
        # có thể nằm TRONG hộp (nhãn X ở y≈285 trong khi hộp tới y=300) hoặc ngoài.
        # An toàn vì _fit() tự loại nhãn không thẳng hàng — thà quét rộng rồi lọc
        # hơn là quét hẹp rồi mất nhãn (đã mắc: 0 nhãn cho cả 6 ô).
        # Vùng tìm nhãn ĐO TỪ DỮ LIỆU, không đoán. Đo trên trang 22 catalog AC:
        #   nhãn Y ở cx ≈ x0+30, cy từ y1-164 đến y1-23
        #   nhãn X ở cy ≈ y1-18,  cx từ x0+36 đến x0+234
        # Hai băng CHỒNG NHAU ở góc dưới-trái (nhãn "0" của cả hai trục), nên phải
        # cắt băng Y trên nhãn X một chút — nếu không, nhãn X cỡ lớn (2000, 20000)
        # lọt vào hồi quy trục Y và cho hệ số vô nghĩa.
        xt = _ticks(ws, "x", (x0 + 20, y1 - 26, x1 + 30, y1 - 10))
        yt = _ticks(ws, "y", (x0 + 14, y0 - 20, x0 + 46, y1 - 20))
        fx, fy = _fit(xt), _fit(yt)
        title = _title_for(ws, box, used_titles)
        if title:
            used_titles.add(title)
        pan = {"title": title, "box": [round(v, 1) for v in (x0, y0, x1, y1)],
               "n_curves": len(qs),
               "x_ticks": [v for _, v in xt], "y_ticks": [v for _, v in yt],
               "x_unit": axis_label(ws, (x0 - 30, y1, x1 + 30, y1 + 50)),
               "y_unit": axis_label(ws, (x0 - 70, y0 - 14, x0 + 14, y1)),
               "series": []}
        if not fx or not fy:
            pan["error"] = (f"chưa hiệu chuẩn được trục (X:{len(xt)} nhãn, "
                            f"Y:{len(yt)} nhãn — cần ≥3 mỗi trục, thẳng hàng)")
            panels.append(pan)
            continue
        ax, bx = fx; ay, by = fy
        for q in sorted(qs, key=len, reverse=True):
            pts = sorted(q)
            step = max(1, len(pts) // samples)
            data = [[round(ax * px + bx, 1), round(ay * py + by, 3)]
                    for px, py in pts[::step]]
            if len(data) >= 3:
                pan["series"].append(data)
        panels.append(pan)

    good = [p for p in panels if p.get("series")]
    return {"ok": bool(good), "page": page, "n_curves": len(curves),
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
