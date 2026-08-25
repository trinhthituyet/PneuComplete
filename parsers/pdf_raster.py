"""Dò đường cong từ đồ thị dạng ẢNH trong PDF — cho trang không có vector.

VÌ SAO CẦN: đo được 9/72 ô đồ thị FRL là ảnh raster nhúng, không phải vector
(es40-74-AWM-AWD-D.pdf tr8: hai ảnh xám 1842×557 và 1848×557 @250dpi).
`pdftocairo -svg` không cho đường cong nào ở đó nên bộ số hoá vector bó tay.

ĐIỀU QUYẾT ĐỊNH TÍNH KHẢ THI: **nhãn trục vẫn nằm ở LỚP TEXT của PDF**, chỉ hình
vẽ là ảnh. Đo được 106 nhãn số ở tr8. Nghĩa là toàn bộ phần hiệu chuẩn, gán ô,
đọc tiêu đề và cỡ cửa GIỮ NGUYÊN — chỉ thay nguồn đường cong. Nếu nhãn cũng nằm
trong ảnh thì phải OCR, và tôi sẽ không làm.

Hàm này trả về ĐÚNG ĐỊNH DẠNG của pdf_chart.svg_paths: [(điểm ở toạ độ TRANG,
nét_đứt)] — nên digitize() dùng lại được không sửa gì.

    python3 -m parsers.pdf_raster <pdf> <trang>

── KHÔNG DÙNG THƯ VIỆN NGOÀI ────────────────────────────────────────────────
PNG xám 8-bit giải nén bằng zlib + bỏ bộ lọc theo dòng, cả hai đều là stdlib.
Dự án này chỉ phụ thuộc stdlib + PyYAML, thêm Pillow chỉ vì một trang là không
đáng.
"""
import base64
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DARK = 128          # ngưỡng nhị phân hoá; ảnh có 461k điểm ở mức 255 và 31k ở 0
MIN_RUN = 1         # nét mảnh nhất vẫn phải bắt
MAX_RUN = 12        # đoạn dày hơn nét vẽ → là khối đặc, không phải đường cong


def _unfilter(raw, w, h, bpp):
    """Bỏ bộ lọc PNG theo dòng (type 0..4). Trả list[bytearray] mỗi dòng w*bpp byte.

    bpp = số byte mỗi điểm ảnh; bộ lọc Sub/Paeth tham chiếu điểm TRƯỚC ĐÓ nên
    phải lùi đúng bpp byte, không phải 1. Ảnh nhúng trong SVG của pdftocairo là
    RGB (colortype 2, bpp=3) dù pdfimages xuất ra bản xám — hai đường khác nhau.
    """
    stride = w * bpp
    out, prev, pos = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[pos]; pos += 1
        line = bytearray(raw[pos:pos + stride]); pos += stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + (a + prev[x]) // 2) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc
                                      else b if pb <= pc else c)) & 255
        out.append(line)
        prev = line
    return out


def read_png_gray(data):
    """PNG 8-bit xám (ct 0) hoặc RGB (ct 2) → (w, h, list dòng ĐỘ XÁM). None nếu khác."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    i, idat, w, h, bd, ct = 8, b"", None, None, None, None
    while i < len(data):
        ln = struct.unpack(">I", data[i:i + 4])[0]
        typ = data[i + 4:i + 8]
        if typ == b"IHDR":
            w, h, bd, ct = struct.unpack(">IIBB", data[i + 8:i + 18])
        elif typ == b"IDAT":
            idat += data[i + 8:i + 8 + ln]
        elif typ == b"IEND":
            break
        i += 12 + ln
    if not (w and bd == 8 and ct in (0, 2)):
        return None                      # chỉ 8-bit xám/RGB; dạng khác thì BÁO KHÔNG
    bpp = 1 if ct == 0 else 3
    rows = _unfilter(zlib.decompress(idat), w, h, bpp)
    if bpp == 1:
        return w, h, [bytes(r) for r in rows]
    # RGB → độ xám. Đồ thị catalog in đen trắng nên lấy kênh nào cũng được, nhưng
    # dùng trung bình để không phụ thuộc giả định đó.
    gray = [bytes((r[i] + r[i + 1] + r[i + 2]) // 3 for i in range(0, len(r), 3))
            for r in rows]
    return w, h, gray


def images_on_page(pdf, page):
    """Ảnh nhúng + ma trận đặt lên trang. Trả [(w, h, dòng, matrix)].

    Lấy CẢ HAI từ SVG: thẻ <image> mang dữ liệu base64, thẻ <use> mang transform.
    Ghép hai thứ theo id — không đoán thứ tự.
    """
    svg = subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page),
                          str(pdf), "-"], capture_output=True, text=True).stdout
    place = {}
    for m in re.finditer(r'<use[^>]*xlink:href="#([^"]+)"[^>]*'
                         r'transform="matrix\(([^)]*)\)"', svg):
        v = [float(x) for x in re.split(r"[ ,]+", m.group(2).strip())]
        if len(v) == 6:
            place[m.group(1)] = v
    out = []
    for m in re.finditer(r'<image id="([^"]+)"[^>]*xlink:href="data:image/png;base64,'
                         r'([^"]+)"', svg):
        mat = place.get(m.group(1))
        if not mat:
            continue                     # ảnh không được đặt lên trang → bỏ qua
        got = read_png_gray(base64.b64decode(m.group(2)))
        if got:
            out.append((got[0], got[1], got[2], mat))
    return out


def _grid_rows_cols(img, x0, x1, y0, y1, frac=0.45):
    """Hàng/cột gần như kín điểm tối TRONG MỘT Ô = KHUNG hoặc LƯỚI.

    PHẢI ĐO THEO TỪNG Ô, không theo cả ảnh. Một ảnh chứa 3 ô cạnh nhau nên vạch
    lưới của một ô chỉ phủ ~1/3 chiều rộng ảnh: đo trên cả ảnh cho 0 hàng lưới,
    đo trong dải một ô cho 14. Không loại thì mọi vạch lưới thành 'đường cong'.
    """
    ww, hh = x1 - x0, y1 - y0
    rows = {y for y in range(y0, y1)
            if sum(1 for x in range(x0, x1) if img[y][x] < DARK) > frac * ww}
    cols = {x for x in range(x0, x1)
            if sum(1 for y in range(y0, y1) if img[y][x] < DARK) > frac * hh}
    return rows, cols


def _runs(img, x, y0, h, grid_rows):
    """Các đoạn tối liên tiếp trên cột x trong [y0, h), trả tâm mỗi đoạn."""
    out, y = [], y0
    while y < h:
        if img[y][x] < DARK:
            s = y
            while y < h and img[y][x] < DARK:
                y += 1
            n = y - s
            if MIN_RUN <= n <= MAX_RUN and not all(v in grid_rows for v in range(s, y)):
                out.append((s + y - 1) / 2.0)
        else:
            y += 1
    return out


def trace(img, w, h, step=2, max_jump=6.0, min_len=12, box=None):
    """Nối các điểm thành đường cong. Trả [[(x, y)…]] ở TOẠ ĐỘ ẢNH.

    Thuật toán tối giản, có chủ ý: quét theo cột rồi nối điểm gần nhất theo y.
    Đồ thị catalog là các đường TRƠN, GẦN NHƯ ĐƠN ĐIỆU và không cắt nhau nhiều —
    nên không cần gì phức tạp hơn. `max_jump` là bước nhảy y tối đa giữa hai cột
    kề: lớn quá thì hai đường khác nhau bị nối làm một.
    """
    x0, y0, x1, y1 = box or (0, 0, w, h)
    grid_rows, grid_cols = _grid_rows_cols(img, x0, x1, y0, y1)
    active, done = [], []
    for x in range(x0, x1, step):
        if x in grid_cols:
            continue
        pts = _runs(img, x, y0, y1, grid_rows)
        used = set()
        for cur in active:
            best, bd = None, max_jump
            for i, y in enumerate(pts):
                if i in used:
                    continue
                d = abs(y - cur[-1][1])
                if d < bd:
                    best, bd = i, d
            if best is None:
                cur.append(None)          # đánh dấu đứt quãng
            else:
                used.add(best)
                cur.append((x, pts[best]))
        # đường mới bắt đầu từ điểm chưa ai nhận
        for i, y in enumerate(pts):
            if i not in used:
                active.append([(x, y)])
        # đường đứt quá 3 cột liên tiếp thì đóng lại
        keep = []
        for cur in active:
            tail = cur[-3:]
            if len(tail) == 3 and all(p is None for p in tail):
                seg = [p for p in cur if p]
                if len(seg) >= min_len:
                    done.append(seg)
            else:
                keep.append([p for p in cur if p] or cur)
        active = [c for c in keep if c]
    for cur in active:
        seg = [p for p in cur if p]
        if len(seg) >= min_len:
            done.append(seg)
    # ── BỎ ĐOẠN NẰM NGANG ────────────────────────────────────────────────────
    # Vạch lưới còn sót (bị đường cong che nên không đủ độ phủ) thành "đường"
    # có y KHÔNG ĐỔI. Đo được: ô AWM20-D ra 33 đường, phần lớn là y 0,600→0,600
    # lặp 3–6 lần vì nét lưới dày 3px bị quét thành 3 đường song song.
    # Đồ thị lưu lượng→áp ra luôn DỐC XUỐNG, nên nằm ngang tuyệt đối là lưới.
    out = []
    for seg in done:
        ys = [y for _, y in seg]
        if max(ys) - min(ys) < 2.0:
            continue
        out.append(seg)
    return _merge_parallel(out)


def _merge_parallel(segs, tol=4.0):
    """Gộp các đường SONG SONG SÁT NHAU thành một.

    Nét vẽ dày ~3px nên quét theo cột cho ra 3 đoạn tối cạnh nhau, và bộ nối
    biến chúng thành 3 'đường' gần trùng khít. Đo được: ô AWM20-D ra 21 đường =
    7 mức áp đặt × 3 bản sao, mảnh nào cũng cùng dải x.

    Gộp bằng cách so y tại các x CHUNG: lệch trung bình < tol thì là một đường,
    và lấy TRUNG BÌNH — tâm nét chính xác hơn mép trên hay mép dưới.
    """
    groups = []
    for seg in sorted(segs, key=len, reverse=True):
        d = {x: y for x, y in seg}
        for g in groups:
            common = [x for x in d if x in g["d"]]
            if len(common) >= max(5, 0.5 * min(len(d), len(g["d"]))):
                dev = sum(abs(d[x] - g["d"][x]) for x in common) / len(common)
                if dev <= tol:
                    g["members"].append(d)
                    break
        else:
            groups.append({"d": d, "members": [d]})
    out = []
    for g in groups:
        acc = {}
        for m in g["members"]:
            for x, y in m.items():
                acc.setdefault(x, []).append(y)
        out.append([(x, sum(v) / len(v)) for x, v in sorted(acc.items())])
    return out


def raster_curves(pdf, page, boxes=None):
    """Đường cong dò từ ảnh, ở TOẠ ĐỘ TRANG. Trả [(điểm, nét_đứt=False)].

    Cùng định dạng với pdf_chart.svg_paths nên digitize() dùng thẳng được.
    Nét đứt luôn False: dò ảnh không phân biệt được kiểu nét, nên trang có chú
    giải theo nét sẽ KHÔNG dùng được cách này — phải có chú giải một điều kiện.
    """
    out = []
    for w, h, img, mat in images_on_page(pdf, page):
        a, b, c, d, e, f = mat
        # Dò THEO TỪNG Ô nếu biết vị trí ô: lưới và biên chỉ nhận ra được trong
        # phạm vi một ô, và dò cả ảnh thì đường của ba ô cạnh nhau bị nối liền.
        # `boxes` ở TOẠ ĐỘ TRANG → đổi ngược về toạ độ ảnh bằng ma trận đặt ảnh.
        # CHỈ dò những ô NẰM TRONG ảnh này. Một trang có thể có nhiều ảnh, mỗi
        # ảnh phủ MỘT hàng ô (đo tr8: ảnh0 phủ cy 102..262, ảnh1 phủ 265..425).
        # Chiếu ô của hàng khác vào ảnh này thì toạ độ rơi ra ngoài hoặc trùng
        # vùng sai, và mỗi đường bị nhân lên theo số ô — đo được 21 đường cho
        # một ô chỉ có 7 mức áp đặt.
        spans = []
        for L, T, R_, B_ in (boxes or []):
            ix0, ix1 = (L - e) / a, (R_ - e) / a
            iy0, iy1 = (T - f) / d, (B_ - f) / d
            if iy1 < iy0:
                iy0, iy1 = iy1, iy0
            if not (-2 <= ix0 and ix1 <= w + 2 and -2 <= iy0 and iy1 <= h + 2):
                continue                  # ô không thuộc ảnh này
            ix0, ix1 = max(0, int(ix0) - 2), min(w, int(ix1) + 3)
            iy0, iy1 = max(0, int(iy0) - 2), min(h, int(iy1) + 3)
            if ix1 - ix0 > 20 and iy1 - iy0 > 20:
                spans.append((ix0, iy0, ix1, iy1))
        for bx in (spans or [None]):
            for seg in trace(img, w, h, box=bx):
                out.append(([(a * x + c * y + e, b * x + d * y + f)
                             for x, y in seg], False))
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    pdf, page = argv[0], int(argv[1])
    imgs = images_on_page(pdf, page)
    print(f"{len(imgs)} ảnh nhúng")
    for w, h, img, mat in imgs:
        segs = trace(img, w, h)
        print(f"  {w}×{h} @({mat[4]:.0f},{mat[5]:.0f}) tỉ lệ {mat[0]:.4f} "
              f"→ {len(segs)} đường")
        for s in sorted(segs, key=len, reverse=True)[:8]:
            print(f"     {len(s):4} điểm  x {s[0][0]}..{s[-1][0]}  "
                  f"y {min(p[1] for p in s):.0f}..{max(p[1] for p in s):.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
