"""Runner: init → seed → crawl → parse. Chạy lại được, tiếp tục đúng chỗ cũ.

    python3 -m crawler.run init
    python3 -m crawler.run crawl          # crawl toàn bộ HTML, PDF chỉ xếp hàng đợi
    python3 -m crawler.run crawl --limit 20
    python3 -m crawler.run stats

Trạng thái nằm trong DB nên Ctrl-C rồi chạy lại là tiếp tục, không cần logic resume.
PDF không được tải ở lệnh `crawl` — chúng nằm ở state='pending', kind='pdf'.
"""
import json
import sys
import time

from . import db, discover, fetcher

sys.path.insert(0, str(db.ROOT))
from parsers import html_index, html_series  # noqa: E402

HTML_KINDS = ("index_letter", "category", "subcategory", "series", "accessory", "other")


def cmd_init():
    con = db.init()
    print(f"DB: {db.DB_PATH}")
    n = discover.seed(con, db.enqueue)
    print(f"seed: {n} URL vào hàng đợi (26 index A-Z + 1 category cho mega-menu)")
    con.close()


def _handle(con, t, res):
    """Parse một bản tải theo kind. Trả dict thống kê ngắn."""
    body = res["body"]
    src = con.execute(
        "select source_doc_id from crawl_fetch where id=?", (res["fetch_id"],)
    ).fetchone()["source_doc_id"]

    # khám phá link ở mọi trang HTML (mega-menu chứa toàn bộ cây)
    found = 0
    for url, kind, sid in discover.links(body.decode("utf-8", "replace"), t["url"]):
        prio = {"index_letter": 10, "category": 60, "subcategory": 70,
                "series": 100, "pdf": 200}.get(kind, 150)
        found += db.enqueue(con, url, kind, series_code=sid,
                            depth=t["depth"] + 1, priority=prio, parent=t["id"])

    info = {"new_urls": found}

    if t["kind"] == "index_letter":
        run = db.start_run(con, res["fetch_id"], html_index.NAME, html_index.VERSION)
        rows = html_index.parse(body)
        n_s, n_c = html_index.load(con, run, rows, source_id=src)
        # chữ không có series nào thì trang trả về layout rỗng (thật tế: B) —
        # ghi 'partial' để phân biệt với lỗi parser
        db.finish_run(con, run, "ok" if rows else "partial", rows_out=len(rows),
                      log={"series_new": n_s, "categories_new": n_c,
                           "note": None if rows else "trang không có bảng kết quả"})
        info |= {"rows": len(rows), "series_new": n_s, "cat_new": n_c}

    elif t["kind"] == "series":
        run = db.start_run(con, res["fetch_id"], html_series.NAME, html_series.VERSION)
        data = html_series.parse(body, t["url"])
        cid = t["series_code"] or discover.series_id_from(t["url"])
        r = html_series.load(con, run, data, t["url"], cid,
                             source_id=src, enqueue=db.enqueue)
        db.finish_run(con, run, "ok", rows_out=r["variations"] + r["suffix_options"],
                      rows_flagged=r["flagged"], log=r)
        info |= r

    con.commit()
    return info


def cmd_crawl(limit=None):
    con = db.connect()
    done = failed = 0
    t0 = time.time()
    while True:
        if limit and done + failed >= limit:
            break
        batch = [r for k in HTML_KINDS for r in db.next_batch(con, 1, kind=k)]
        if not batch:
            break
        t = batch[0]
        con.execute("update crawl_target set state='fetching' where id=?", (t["id"],))
        con.commit()
        res = fetcher.fetch(con, t)
        if res is None:
            failed += 1
            print(f"  ✗ {t['kind']:13} {t['url'][:88]}", flush=True)
            continue
        info = _handle(con, t, res)
        done += 1
        pend = con.execute(
            "select count(*) n from crawl_target where state='pending' and kind<>'pdf'"
        ).fetchone()["n"]
        bits = " ".join(f"{k}={v}" for k, v in info.items() if v)
        print(f"  ✓ [{done:4}] pend={pend:4} {t['kind']:13} "
              f"{t['url'][-70:]:70} {bits}", flush=True)

    el = time.time() - t0
    print(f"\nxong: {done} tải được, {failed} lỗi, {el/60:.1f} phút")
    print(json.dumps(db.stats(con), indent=2, ensure_ascii=False))
    con.close()


def _purge_old_versions(con, parser_name, version):
    """Xoá kết quả của phiên bản parser cũ. extract_run xoá theo cascade sẽ
    kéo theo review_item — nhờ vậy sửa parser rồi chạy lại không để lại rác."""
    n = con.execute(
        "delete from extract_run where parser_name=? and parser_version<>?",
        (parser_name, version),
    ).rowcount
    con.commit()
    return n


def _todo(con, parser_name, version, url_like=None, kind=None):
    q = """select f.id fid, f.body_path, f.source_doc_id, t.url, t.series_code
           from crawl_fetch f join crawl_target t on t.id = f.target_id
           where t.state='done'
             and not exists (select 1 from extract_run e
                             where e.fetch_id=f.id and e.parser_name=?
                               and e.parser_version=? and e.status='ok')"""
    args = [parser_name, version]
    if url_like:
        q += " and t.url like ?"
        args.append(url_like)
    if kind:
        q += " and t.kind=?"
        args.append(kind)
    return con.execute(q, args).fetchall()


def cmd_reparse():
    """Tầng 2 chạy lại trên cache — 0 request.

    Sửa parser rồi chạy lại lệnh này: kết quả phiên bản cũ bị xoá, toàn bộ trang
    trong cache được parse lại. Đây là lợi ích chính của việc tách crawl khỏi parse.
    """
    from parsers import html_subcat

    con = db.connect()

    # ── trang series ────────────────────────────────────────────────────────
    d = _purge_old_versions(con, html_series.NAME, html_series.VERSION)
    rows = _todo(con, html_series.NAME, html_series.VERSION, kind="series")
    print(f"[series]  xoá {d} run cũ · parse {len(rows)} trang")
    tot = {"variations": 0, "suffix_options": 0, "flagged": 0, "pdfs_queued": 0}
    for i, r in enumerate(rows, 1):
        p = db.ROOT / r["body_path"]
        if not p.exists():
            continue
        run = db.start_run(con, r["fid"], html_series.NAME, html_series.VERSION)
        data = html_series.parse(p.read_bytes(), r["url"])
        cid = r["series_code"] or discover.series_id_from(r["url"])
        res = html_series.load(con, run, data, r["url"], cid,
                               source_id=r["source_doc_id"], enqueue=db.enqueue)
        db.finish_run(con, run, "ok", rows_out=res["variations"] + res["suffix_options"],
                      rows_flagged=res["flagged"], log=res)
        for k in tot:
            tot[k] += res.get(k, 0)
        if i % 300 == 0 or i == len(rows):
            print(f"   [{i:5}/{len(rows)}] {json.dumps(tot)}", flush=True)

    # ── trang subcategory ?view=list ────────────────────────────────────────
    d = _purge_old_versions(con, html_subcat.NAME, html_subcat.VERSION)
    idx = html_subcat.build_index(con)
    rows = _todo(con, html_subcat.NAME, html_subcat.VERSION, url_like="%view=list%")
    print(f"[?view=list]  xoá {d} run cũ · chỉ mục {len(idx)} khoá · parse {len(rows)} trang")
    tot2 = {"flagged": 0, "unmatched": 0, "proposed_series": 0,
            "variations": 0, "suffix_options": 0}
    for i, r in enumerate(rows, 1):
        p = db.ROOT / r["body_path"]
        if not p.exists():
            continue
        run = db.start_run(con, r["fid"], html_subcat.NAME, html_subcat.VERSION)
        data = html_subcat.parse(p.read_bytes(), r["url"])
        res = html_subcat.load(con, run, data, r["url"], idx)
        db.finish_run(con, run, "ok", rows_out=res["variations"] + res["suffix_options"],
                      rows_flagged=res["flagged"], log=res)
        for k in tot2:
            tot2[k] += res[k]
        if i % 150 == 0 or i == len(rows):
            print(f"   [{i:4}/{len(rows)}] {json.dumps(tot2)}", flush=True)

    print("\nseries pages:", json.dumps(tot, ensure_ascii=False))
    print("view=list   :", json.dumps(tot2, ensure_ascii=False))
    con.close()


def cmd_backfill():
    """Gán category cho series phát hiện qua mega-menu (không có trong indexSearch).

    indexSearch cho category dạng chữ ('Air Cylinders/Standard...'), còn mega-menu
    chỉ cho URL. Suy category từ đoạn path thứ 3 của URL.
    """
    con = db.connect()
    rows = con.execute(
        """select id, url from series
           where category_id is null and url like '%/webcatalog/en-jp/%'"""
    ).fetchall()
    fixed = 0
    for r in rows:
        parts = [s for s in r["url"].split("?")[0].split("/") if s]
        try:
            slug = parts[parts.index("en-jp") + 1]
        except (ValueError, IndexError):
            continue
        if slug in ("seriesList", "indexSearch"):
            continue
        name = slug.replace("-", " ").title()
        con.execute(
            "insert or ignore into category (code, name, layer) values (?,?,?)",
            (slug, name, html_index.layer_of(name)),
        )
        cat = con.execute("select id from category where code=?", (slug,)).fetchone()
        con.execute("update series set category_id=?, category_raw=coalesce(category_raw,?) "
                    "where id=?", (cat["id"], name, r["id"]))
        fixed += 1
    con.commit()
    left = con.execute(
        "select count(*) n from series where category_id is null"
    ).fetchone()["n"]
    print(f"gán category cho {fixed} series · còn thiếu {left}")
    con.close()


SLICE = ["CM2-CDM2-Z-E", "CJ2-CDJ2-Z-E", "SY-E", "AS-E-E", "AS-FS-E",
         "TU-E", "AC-A-E", "D-M9-5-E"]


def cmd_pdf(only_slice=True, limit=None):
    """Tải PDF từ hàng đợi. Mặc định chỉ bộ SLICE (pha 3), không tải cả 1.252 file.

        python3 -m crawler.run pdf              # chỉ bộ SLICE
        python3 -m crawler.run pdf --all        # toàn bộ hàng đợi PDF
    """
    con = db.connect()
    if only_slice:
        marks = ",".join("?" * len(SLICE))
        rows = con.execute(
            f"""select * from crawl_target where kind='pdf' and state='pending'
                and series_code in ({marks}) order by priority""", SLICE).fetchall()
    else:
        rows = con.execute(
            "select * from crawl_target where kind='pdf' and state='pending' "
            "order by priority, id").fetchall()
    if limit:
        rows = rows[:limit]
    print(f"tải {len(rows)} PDF" + (" (bộ SLICE)" if only_slice else " (toàn bộ)"))

    mb = 0.0
    for i, t in enumerate(rows, 1):
        con.execute("update crawl_target set state='fetching' where id=?", (t["id"],))
        con.commit()
        res = fetcher.fetch(con, t)
        if res is None:
            print(f"  ✗ {t['series_code']}  {t['url'][-60:]}", flush=True)
            continue
        n = len(res["body"]) / 1e6
        mb += n
        # số trang: đếm nhanh bằng chuỗi trong PDF, không cần thư viện ngoài
        pages = res["body"].count(b"/Type /Page") + res["body"].count(b"/Type/Page")
        con.execute("update source_doc set page_count=?, kind='pdf' where sha256=?",
                    (pages or None, res["sha"]))
        con.commit()
        print(f"  ✓ [{i}/{len(rows)}] {str(t['series_code']):14} "
              f"{n:6.1f} MB  ~{pages:4} trang  {t['url'][-46:]}", flush=True)

    print(f"\nxong: {mb:.1f} MB")
    con.close()


def cmd_grammar():
    """PDF đã tải → code_slot/code_option. Chạy lại được (xoá run phiên bản cũ).

    Hiện chỉ CM2 ra ngữ pháp đầy đủ; các series khác spine không khớp và đi vào
    review_item — xem docs/CRAWL-RESULTS.md phần "chỉ 1/8 PDF chạy được".
    """
    from parsers import pdf_how_to_order as H

    con = db.connect()
    _purge_old_versions(con, H.NAME, H.VERSION)
    rows = con.execute(
        """select f.id fid, f.body_path, f.source_doc_id, t.series_code
           from crawl_fetch f join crawl_target t on t.id=f.target_id
           where t.kind='pdf' and t.state='done' and t.series_code is not null"""
    ).fetchall()
    print(f"PDF cần dựng ngữ pháp: {len(rows)}")
    for r in rows:
        path = db.ROOT / r["body_path"]
        if not path.exists():
            continue
        sr = con.execute("select id from series where catalog_id=?",
                         (r["series_code"],)).fetchone()
        if not sr:
            print(f"  ⊘ {r['series_code']}: không có series tương ứng")
            continue
        hint = r["series_code"].split("-")[0]
        pages = H.pages_with_hto(path)
        if not pages:
            print(f"  ⊘ {r['series_code']}: không thấy trang How to Order")
            continue
        run = db.start_run(con, r["fid"], H.NAME, H.VERSION)
        data = H.parse(path, pages[0], series_hint=hint)
        res = H.load(con, run, data, sr["id"], source_page=pages[0])
        db.finish_run(con, run, "ok" if res["slots"] else "partial",
                      rows_out=res["slots"], rows_flagged=res["reviews"], log=res)
        mark = "✓" if res["slots"] else "✗"
        print(f"  {mark} {r['series_code']:16} trang {pages[0]:4}  "
              f"slot={res['slots']} option={res['options']} review={res['reviews']}")
    con.close()


def cmd_stats():
    con = db.connect()
    print(json.dumps(db.stats(con), indent=2, ensure_ascii=False))
    con.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    lim = None
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
    {"init": cmd_init, "crawl": lambda: cmd_crawl(lim),
     "reparse": cmd_reparse, "backfill": cmd_backfill, "grammar": cmd_grammar,
     "pdf": lambda: cmd_pdf("--all" not in sys.argv, lim),
     "stats": cmd_stats}[cmd]()
