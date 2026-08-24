"""Dựng lại hàng đợi PDF từ cache — không cần mạng.

VÌ SAO CÓ TỆP NÀY: `crawl_fetch` và `crawl_target` mất trong sự cố pneu.db, nên
`crawler.run reparse` không còn danh sách việc để duyệt, và 974 MB cache thành
bytes mồ côi. Nhưng chính nội dung cache mang đủ thông tin để dựng lại:

    2.188 tệp HTML  →  link /catalog/**.pdf  →  crawler/discover.series_id_from()
                                              →  catalog ID  →  crawl_target

ĐO TRƯỚC KHI VIẾT — cache KHÔNG cho ngữ pháp mã:
    1.936 trang không có bảng nào (trang tìm kiếm, điều hướng)
      249 trang nhiều bảng → 45 trang thật sự cho dữ liệu
        5 trang có How-to-Order
       11 tệp PDF
Reparse toàn bộ chỉ được 575 dòng variation + 651 option hậu tố — đó là DANH MỤC
("có series này, bore này"), không phải NGỮ PHÁP (code_slot + code_option).
Ngữ pháp chỉ đến từ pdf_how_to_order.py (đọc PDF) hoặc grammar_seed.py (YAML tay).

Nên giá trị thật của cache là 2.397 LINK PDF: danh sách chính xác cần tải để có
ngữ pháp. Bước tải bắt buộc phải có mạng nên tệp này chỉ dựng HÀNG ĐỢI.

    python3 -m crawler.rebuild_queue            # xem sẽ thêm gì, không ghi
    python3 -m crawler.rebuild_queue --write    # ghi vào crawl_target
    python3 -m crawler.rebuild_queue --report   # xếp ưu tiên theo BOM thật
"""
import collections
import re
import sys
from pathlib import Path

from crawler import db, discover

PDF_HREF = re.compile(r'href="([^"]*?/catalog/[^"]*?\.pdf)"', re.I)


def scan_cache(cache_dir=None):
    """Quét cache, trả {catalog_id: {url,...}} và số trang đã đọc."""
    cache_dir = Path(cache_dir or db.CACHE_DIR)
    found = collections.defaultdict(set)
    n_page = n_link = 0
    for f in sorted(cache_dir.rglob("*.html")):
        try:
            doc = f.read_text(errors="replace")
        except OSError:
            continue
        n_page += 1
        for href in set(PDF_HREF.findall(doc)):
            url = href if href.startswith("http") else "https://www.smcworld.com" + href
            n_link += 1
            sid = discover.series_id_from(url)
            if sid:
                found[sid].add(url)
    return found, n_page, n_link


def known_grammars(con):
    """catalog_id đã có ngữ pháp — không cần tải lại."""
    return {r["catalog_id"] for r in con.execute(
        """select distinct s.catalog_id from series s
           where exists (select 1 from code_slot cs where cs.series_id = s.id)""")}


# Tiền tố mã → catalog_id thường gặp. Dùng để nối mã trong BOM thật với họ cần
# tải. Không đoán: chỉ khai những cặp đọc được từ mã thật trong BOM.
PREFIX_HINT = [
    ("AN", "giảm âm (silencer)"),
    ("VT", "van 3 cổng"),
    ("ZP", "pad chân không"),
    ("ZK", "ejector chân không"),
    ("ISE", "cảm biến áp suất"),
    ("KQ2", "đầu nối one-touch"),
    ("KSL", "đầu nối xoay"),
    ("AR", "điều áp"),
    ("AF", "lọc khí"),
    ("AW", "lọc + điều áp"),
    ("JB", "floating joint JB"),
    ("MHZ", "xy-lanh kẹp"),
    ("CJ", "xy-lanh nhỏ"),
    ("MY", "xy-lanh không cần"),
    ("AMC", "bộ khử ẩm"),
    ("VHS", "van xả áp"),
]


def smc_prefixes(con):
    """Tiền tố mã SMC — suy TỪ DỮ LIỆU, không liệt kê tay.

    Nguồn: 1.300 series đã crawl (cột code và catalog_id). Mã trong BOM không
    khớp tiền tố nào ở đây thì gần như chắc không phải SMC — thực tế là bulông,
    đai ốc, nhôm định hình MISUMI (đo được: 65 họ, 2.068 cái).
    """
    out = set()
    for r in con.execute("select code, catalog_id from series"):
        for v in (r["code"], r["catalog_id"]):
            m = re.match(r"[A-Z]{1,4}\d?", (v or "").upper())
            if m and len(m.group(0)) >= 2:
                out.add(m.group(0))
    return out


def is_smc(code, prefixes):
    """Mã có khớp tiền tố SMC nào không — khớp phải kết thúc ở ranh giới."""
    c = code.upper()
    for p in prefixes:
        if c.startswith(p):
            rest = c[len(p):]
            if rest == "" or rest[0].isdigit() or rest[0] in "-_":
                return True
    return False


def missing_from_bom(con):
    """Mã trong BOM THẬT mà engine chưa parse được, xếp theo số lượng.

    Đây là thứ quyết định thứ tự ưu tiên: thiếu họ hay dùng mới đáng sửa trước.
    Trả (bảng_theo_họ, số_cái_cơ_khí_đã_loại).
    """
    from engine import parser as P
    rows = con.execute(
        """select b.raw_code, sum(b.qty) q, count(distinct b.machine_id) m
           from bom_line b group by b.raw_code""").fetchall()
    by_family = collections.defaultdict(lambda: {"qty": 0, "codes": set(), "machines": 0})
    # LỌC BẰNG DANH SÁCH TRẮNG, không phải danh sách đen.
    # Bản trước liệt kê tiền tố cơ khí cần loại — nó cứ phải nối dài mãi vì BOM
    # còn hàng chục họ MISUMI khác. Đảo lại: chỉ giữ mã khớp tiền tố catalog SMC
    # CÓ THẬT, suy từ 1.300 series đã crawl + catalog ID trong cache. Dữ liệu tự
    # nói, không phải tôi liệt kê tay.
    smc = smc_prefixes(con)
    n_mech = 0
    for r in rows:
        code = (r["raw_code"] or "").strip()
        if not code:
            continue
        if P.parse(con, code).get("ok"):
            continue                       # đã đọc được, không thiếu
        # Bulông/nhôm định hình MISUMI — không phải khí nén, không thuộc phạm vi
        # phần mềm này. Đo được: 65 họ / 2.068 cái. Trộn vào là bảng ưu tiên
        # thành rác và ta đi tải nhầm catalog.
        if not is_smc(code, smc):
            n_mech += r["q"] or 0
            continue
        fam = next((p for p, _ in PREFIX_HINT if code.upper().startswith(p)), None)
        key = fam or re.sub(r"[\d\-].*$", "", code.upper())[:6] or "?"
        d = by_family[key]
        d["qty"] += r["q"] or 0
        d["codes"].add(code)
        d["machines"] = max(d["machines"], r["m"] or 0)
    return by_family, n_mech


def rank_by_bom(con, found):
    """Xếp catalog ID theo việc BOM THẬT của bạn có dùng họ đó không.

    385 họ thiếu ngữ pháp nhưng tải hết là phí: chỉ 57 mã khí nén trong BOM là
    chưa đọc được, và chúng thuộc số ít họ. Ưu tiên đúng những họ đó.
    Trả list (catalog_id, điểm, ghi_chú) — điểm = tổng số lượng trong BOM.
    """
    from engine import parser as P

    smc = smc_prefixes(con)

    unread = []
    for r in con.execute("select raw_code, sum(qty) q from bom_line group by raw_code"):
        c = (r["raw_code"] or "").strip().upper()
        if not c or not is_smc(c, smc):
            continue
        if not P.parse(con, c).get("ok"):
            unread.append((c, r["q"] or 0))

    def match(pre, code):
        # khớp phải kết thúc ở ranh giới: ký tự sau tiền tố là SỐ hoặc '-'.
        # Không có điều kiện này thì "MS" khớp "MSB12" (MISUMI) và "AT" khớp
        # "ATPA16" — cả bảng ưu tiên thành rác.
        if not code.startswith(pre):
            return False
        rest = code[len(pre):]
        return rest == "" or rest[0].isdigit() or rest[0] == "-"

    out = []
    for sid in found:
        pre = sid.split("-")[0].upper()
        if len(pre) < 2:
            continue
        hit = [(c, q) for c, q in unread if match(pre, c)]
        if hit:
            out.append((sid, sum(q for _, q in hit), sorted({c for c, _ in hit})[:3]))

    # Nhiều catalog ID cùng tiền tố (VP-E, VP-3-E, VP-O3-E) thì giữ bản NGẮN nhất
    # — đếm cả ba là nhân ba cùng một nhu cầu.
    best = {}
    for sid, score, ex in out:
        pre = sid.split("-")[0].upper()
        if pre not in best or len(sid) < len(best[pre][0]):
            best[pre] = (sid, score, ex)
    return sorted(best.values(), key=lambda x: -x[1])


def enqueue(con, found, skip_known=True, limit=None, only=None):
    """Đẩy URL PDF vào crawl_target. Trả (số thêm, số bỏ qua)."""
    known = known_grammars(con) if skip_known else set()
    added = skipped = 0
    for sid, urls in sorted(found.items()):
        if sid in known or (only is not None and sid not in only):
            skipped += len(urls)
            continue
        for u in sorted(urls):
            n = db.enqueue(con, u, "pdf", series_code=sid, depth=3, priority=50)
            added += n or 0
            if limit and added >= limit:
                con.commit()
                return added, skipped
    con.commit()
    return added, skipped


def relink_html(con, min_tables=4):
    """Dựng lại crawl_target + crawl_fetch cho trang HTML CÓ NỘI DUNG.

    reparse() duyệt theo crawl_fetch; bảng đó mất nên 974 MB cache thành mồ côi.
    Ở đây tạo lại liên kết trang↔tệp để reparse chạy được, KHÔNG cần mạng.

    Chỉ nhận trang có ≥ min_tables bảng: đo được 1.936/2.188 trang là trang tìm
    kiếm/điều hướng, không mang dữ liệu. Nhận hết thì reparse chạy vô ích và
    extract_run đầy dòng rỗng.

    URL thật đã mất nên dùng URI giả `cache://<sha>` — parser html_series chỉ
    dùng url để ghi nguồn, không dùng để lấy dữ liệu.
    """
    cache_dir = Path(db.CACHE_DIR)
    n_link = n_skip = 0
    for f in sorted(cache_dir.rglob("*.html")):
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        if raw.count(b"<table") < min_tables:
            n_skip += 1
            continue
        sha = f.stem
        uri = f"cache://{sha}"
        db.enqueue(con, uri, "series", series_code=None, depth=3, priority=90)
        t = con.execute("select id from crawl_target where url=?", (uri,)).fetchone()
        if not t:
            continue
        if con.execute("select 1 from crawl_fetch where target_id=?",
                       (t["id"],)).fetchone():
            continue
        con.execute("update crawl_target set state='done' where id=?", (t["id"],))
        db.record_fetch(con, t["id"], status=200, ctype="text/html", sha=sha,
                        path=str(f.relative_to(db.ROOT)), size=len(raw), ms=0)
        n_link += 1
    con.commit()
    return n_link, n_skip


def main(argv):
    con = db.connect()

    if "--report" in argv:
        fams, n_mech = missing_from_bom(con)
        if not fams:
            print("Không có mã nào trong BOM mà engine chưa đọc được.")
            print("(hoặc DB chưa nhập BOM: python3 -m ingest.bom_import BOM/*.xlsx)")
            return 0
        print("HỌ THIẾU NGỮ PHÁP — xếp theo tác động lên BOM THẬT của bạn")
        print("=" * 74)
        print(f"{'họ':10} {'SL':>6} {'máy':>4} {'mã':>4}  mô tả · ví dụ")
        print("-" * 74)
        hint = dict(PREFIX_HINT)
        for fam, d in sorted(fams.items(), key=lambda kv: -kv[1]["qty"]):
            ex = ", ".join(sorted(d["codes"])[:2])
            print(f"{fam:10} {d['qty']:>6.0f} {d['machines']:>4} {len(d['codes']):>4}  "
                  f"{hint.get(fam, ''):<22} {ex[:34]}")
        print()
        print(f"  (đã LOẠI {n_mech:,.0f} cái thuộc họ cơ khí MISUMI — bulông, đai ốc,")
        print("   nhôm định hình. Không phải khí nén, ngoài phạm vi phần mềm.)")
        print()
        print("  SL = tổng số lượng trong BOM · máy = xuất hiện ở mấy máy")
        print("  Thiếu họ hay dùng mới đáng sửa trước — đây là thứ tự nên tải PDF.")
        return 0

    print("Quét cache dựng lại hàng đợi PDF")
    print("=" * 66)
    found, n_page, n_link = scan_cache()
    n_url = sum(len(v) for v in found.values())
    print(f"  {n_page:,} trang HTML · {n_link:,} link PDF · {n_url:,} URL khác nhau")
    print(f"  {len(found)} catalog ID nhận dạng được")
    known = known_grammars(con)
    new = {k: v for k, v in found.items() if k not in known}
    print(f"  {len(known)} họ đã có ngữ pháp → bỏ qua")
    print(f"  {len(new)} họ CHƯA có ngữ pháp → cần tải")

    ranked = rank_by_bom(con, new)
    if ranked:
        print(f"\n  {len(ranked)} họ CÓ TRONG BOM của bạn — nên tải trước:")
        for sid, score, ex in ranked[:12]:
            print(f"    {sid:20} ×{score:<6.0f} {', '.join(ex)[:40]}")

    if "--relink" in argv:
        n, skip = relink_html(con)
        print(f"\n✓ Nối lại {n:,} trang HTML có nội dung (bỏ {skip:,} trang rỗng)")
        print("  Giờ chạy được: python3 -m crawler.run reparse   (0 request)")
        con.close()
        return 0

    if "--write" in argv:
        only = None
        if "--bom-only" in argv:
            only = {sid for sid, _, _ in ranked}
            print(f"\n  --bom-only: chỉ thêm {len(only)} họ có trong BOM")
        added, skipped = enqueue(con, found, only=only)
        print(f"\n✓ Thêm {added:,} URL vào crawl_target (bỏ qua {skipped:,} của họ đã có)")
        print("\nBước tiếp theo CẦN MẠNG — bạn chạy:")
        print("    python3 -m crawler.run pdf")
        print("  Tải ≤1 req/s, tôn trọng robots.txt. Xong thì tôi chạy")
        print("  pdf_how_to_order để sinh ngữ pháp.")
    else:
        top = sorted(new.items(), key=lambda kv: -len(kv[1]))[:15]
        print("\n  Họ có nhiều bản PDF nhất (chưa có ngữ pháp):")
        for sid, urls in top:
            print(f"    {sid:20} {len(urls):3} tệp")
        print("\n  (thêm --write để ghi vào hàng đợi · --report để xếp ưu tiên theo BOM)")
    con.close()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(db.ROOT))
    sys.exit(main(sys.argv[1:]))
