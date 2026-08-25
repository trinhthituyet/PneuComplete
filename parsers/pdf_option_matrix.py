"""Đọc bảng "How to Order" — ma trận KÝ HIỆU × CỠ THÂN — từ PDF catalog.

VÌ SAO CẦN: `requires` trong ngữ pháp mã hiện chỉ phủ 26/483 tuỳ chọn (5%), và
họ FRL bằng 0. Không có ràng buộc thì engine sinh được mã KHÔNG TỒN TẠI mà không
có dấu hiệu gì — đo được: engine đang xuất `AC20B-02DG-D`, trong đó auto drain
`D` (N.O.) catalog ghi `—` cho cỡ 20. Thiếu một dòng thì người ta thấy; một mã
sai thì người ta đặt hàng.

Đây là rủi ro ĐÚNG/SAI, nặng hơn rủi ro THIẾU — nên ưu tiên hơn việc phủ thêm họ.

    python3 -m parsers.pdf_option_matrix <pdf> <trang>        # xem đọc được gì
    python3 -m parsers.pdf_option_matrix <pdf> <trang> --slot # kèm ánh xạ ô

── CẤU TRÚC BẢNG (đo trên es40-69-AC-D.pdf tr20) ────────────────────────────
    hàng tiêu đề    :  20  30  40  50  60          ← cỡ thân, cx 428…541
    mỗi dòng        :  <ký hiệu>  <mô tả>  V/—/…   ← V = có, — = không
    dấu '+'         :  NGĂN NHÓM — mỗi nhóm là một ô mã

KHÔNG TRA ĐƯỢC THEO KÝ HIỆU: ký hiệu TRÙNG giữa các ô. Đo trên AC-D: 'C' có ở cả
`combination` và `auto_drain`; 'D' có ở `combination`, `auto_drain`, và
`series_suffix`; 'Nil' có ở bốn ô. Nên phải gán NHÓM vào ô bằng cách khớp CẢ TẬP
ký hiệu của nhóm với tập tuỳ chọn của ô, không khớp từng cái.
"""
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parsers import pdf_chart                      # noqa: E402

YES = {"V", "v", "✓", "○", "●"}     # dấu "có"
NO = {"—", "–", "-", "―"}           # dấu "không"


def _rows(ws, tol=2.5):
    """Gom từ thành DÒNG theo cy. Trả [(cy, [(cx, text, cao)…])].

    Giữ CHIỀU CAO chữ vì nó phân biệt ký hiệu với số chú thích: đo trên tr20,
    ký hiệu cao 10,7 còn '*1'/'*2' viết trên cao chỉ 5,8. Không lọc thì nhóm đầu
    tiên đọc thành 'Nil/1/2' — hai ràng buộc bịa từ chú thích.
    """
    out = []
    for wx0, wy0, wx1, wy1, t in sorted(ws, key=lambda w: ((w[1] + w[3]) / 2,
                                                           (w[0] + w[2]) / 2)):
        cy, cx = (wy0 + wy1) / 2, (wx0 + wx1) / 2
        if out and abs(cy - out[-1][0]) <= tol:
            out[-1][1].append((cx, t, wy1 - wy0))
        else:
            out.append((cy, [(cx, t, wy1 - wy0)]))
    return [(cy, sorted(items)) for cy, items in out]


def _header(rows, sizes):
    """Hàng tiêu đề cỡ thân. Trả (cy, [(cx, cỡ)…]) hoặc None.

    `sizes` là tập cỡ ĐỌC TỪ DB (ô `size` của chính họ đó) — không liệt kê tay,
    và nhờ vậy nếu catalog dùng bộ cỡ khác thì hàm tự trượt chứ không nhận bừa.
    """
    best = None
    for cy, items in rows:
        hit = [(cx, t) for cx, t, _ in items if t in sizes]
        if len(hit) >= 3 and len({t for _, t in hit}) == len(hit):
            if best is None or len(hit) > len(best[1]):
                best = (cy, hit)
    return best


def _symbol_column(rows, cy0, cols):
    """cx của cột KÝ HIỆU — suy từ dữ liệu, không hardcode.

    Cột ký hiệu là cột token NGẮN nằm bên trái mọi cột dấu, xuất hiện ở nhiều
    dòng nhất. Bản đầu tôi định viết cứng cx≈170 (đo trên đúng trang này) — đó
    là lớp lỗi 'canh theo một trang' đã sửa ba lần ở bộ số hoá đồ thị.
    """
    left = min(cols) - 20
    cnt = collections.Counter()
    for cy, items in rows:
        if cy <= cy0:
            continue
        for cx, t, h in items:
            if cx < left and len(t) <= 3 and t not in NO and t != "+":
                cnt[round(cx / 4) * 4] += 1
    return cnt.most_common(1)[0][0] if cnt else None


def read_matrix(pdf, page, sizes):
    """Đọc bảng. Trả [{"symbols": [(ký_hiệu, {cỡ: bool})…]}…] theo từng NHÓM.

    Nhóm ngăn bởi dấu '+'. Dòng không có dấu nào ở cột cỡ thì bỏ (dòng mô tả
    tràn xuống).
    """
    ws = pdf_chart.words(pdf, page)
    rows = _rows(ws)
    hdr = _header(rows, set(sizes))
    if not hdr:
        return None, "không thấy hàng tiêu đề cỡ thân"
    cy0, cols = hdr
    xsym = _symbol_column(rows, cy0, [cx for cx, _ in cols])
    if xsym is None:
        return None, "không thấy cột ký hiệu"

    # ── GHÉP KÝ HIỆU VỚI DẤU THEO BƯỚC HÀNG, không theo cùng-một-dòng ────────
    # Ký hiệu và dấu V/— của CÙNG một hàng bảng lệch nhau vài px trong PDF (đo:
    # 'E2' ở cy=457,3 còn năm dấu V ở cy=460,2 — lệch 2,9). Gộp theo dung sai cố
    # định thì hàng nào lệch quá ngưỡng là MẤT, mà mất một hàng là mất một ràng
    # buộc — im lặng. Nới ngưỡng cho vừa trang này lại đúng lớp lỗi 'canh theo
    # một trang'. Nên: đo BƯỚC HÀNG từ chính bảng rồi ghép trong nửa bước.
    marks_rows, sym_rows, plus_cy = [], [], []
    for cy, items in rows:
        if cy <= cy0:
            continue
        if any(t == "+" for _, t, _ in items):
            plus_cy.append(cy)
        marks = {}
        for cx_h, sz in cols:
            m = [t for cx, t, _ in items
                 if abs(cx - cx_h) < 9 and (t in YES or t in NO)]
            if m:
                marks[sz] = m[0] in YES
        if len(marks) >= len(cols) - 1:
            marks_rows.append((cy, marks))
        for cx, t, h in items:
            if (abs(cx - xsym) < 12 and t not in YES and t not in NO
                    and t not in ("*", "+")):
                sym_rows.append((cy, t, h))

    if len(marks_rows) < 2 or not sym_rows:
        return None, "không đọc được hàng dữ liệu nào"
    # LOẠI SỐ CHÚ THÍCH bằng CHIỀU CAO chữ, ngưỡng suy từ chính bảng (trung vị).
    hs = sorted(h for _, _, h in sym_rows)
    hmed = hs[len(hs) // 2]
    sym_rows = [(cy, t) for cy, t, h in sym_rows if h >= 0.8 * hmed]
    diffs = sorted(b[0] - a[0] for a, b in zip(marks_rows, marks_rows[1:])
                   if b[0] - a[0] > 1)
    pitch = diffs[len(diffs) // 2] if diffs else 10.0

    paired = []
    for cy, marks in marks_rows:
        near = [(abs(sy - cy), s) for sy, s in sym_rows if abs(sy - cy) <= pitch * 0.45]
        if near:
            paired.append((cy, min(near)[1], marks))

    groups, cur, pi = [], [], 0
    for cy, sym, marks in paired:
        while pi < len(plus_cy) and plus_cy[pi] < cy:
            if cur:
                groups.append(cur)
                cur = []
            pi += 1
        cur.append((sym, marks))
    if cur:
        groups.append(cur)
    return groups, None


def map_groups(groups, slot_options):
    """Gán mỗi NHÓM vào một Ô mã, bằng cách khớp CẢ TẬP ký hiệu.

    slot_options: {tên_ô: {mã…}} đọc từ DB.

    Khớp từng ký hiệu là sai: 'D' có ở ba ô khác nhau trong AC-D. Dùng Jaccard
    trên cả tập, và mỗi ô chỉ nhận MỘT nhóm (nhóm điểm cao lấy trước).
    """
    pairs = []
    for gi, g in enumerate(groups):
        syms = {s for s, _ in g}
        for slot, opts in slot_options.items():
            inter = len(syms & opts)
            if not inter:
                continue
            pairs.append((inter / len(syms | opts), gi, slot))
    pairs.sort(reverse=True)
    used_g, used_s, out = set(), set(), {}
    for score, gi, slot in pairs:
        if gi in used_g or slot in used_s:
            continue
        used_g.add(gi)
        used_s.add(slot)
        out[slot] = (gi, round(score, 3))
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    from crawler import db
    pdf, page = argv[0], int(argv[1])
    cid = argv[2] if len(argv) > 2 else "AC-D-E"
    con = db.connect()
    opts = collections.defaultdict(set)
    for r in con.execute(
            """select cs.name slot, o.code from code_option o
               join code_slot cs on cs.id = o.slot_id
               join series s on s.id = cs.series_id where s.catalog_id = ?""", (cid,)):
        opts[r["slot"]].add(r["code"])
    con.close()
    sizes = opts.get("size", set())
    groups, err = read_matrix(pdf, page, sizes)
    if err:
        print(f"✗ {err}")
        return 1
    print(f"{len(groups)} nhóm, cỡ thân {sorted(sizes)}")
    mapped = map_groups(groups, dict(opts))
    rev = {gi: (slot, sc) for slot, (gi, sc) in mapped.items()}
    for gi, g in enumerate(groups):
        slot, sc = rev.get(gi, ("(chưa gán)", 0))
        print(f"  nhóm {gi} → {slot} (khớp {sc})")
        for sym, marks in g:
            ok = [s for s, v in marks.items() if v]
            print(f"     {sym:5} có ở: {','.join(sorted(ok, key=int)) or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
