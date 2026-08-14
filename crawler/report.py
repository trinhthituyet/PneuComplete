"""Báo cáo nội dung DB sau crawl.   python3 -m crawler.report"""
import sys

from . import db


def main():
    con = db.connect()
    q = lambda s, *a: con.execute(s, a).fetchall()          # noqa: E731
    one = lambda s, *a: con.execute(s, a).fetchone()[0]     # noqa: E731

    print("═" * 74)
    print("HÀNG ĐỢI CRAWL")
    print("═" * 74)
    for r in q("""select kind, state, count(*) n, sum(coalesce(f.byte_size,0)) b
                  from crawl_target t left join crawl_fetch f on f.target_id=t.id
                  group by kind, state order by kind, state"""):
        mb = f"{r['b']/1e6:8.1f} MB" if r["b"] else ""
        print(f"  {r['kind']:14} {r['state']:9} {r['n']:6}  {mb}")

    print("\n" + "═" * 74)
    print("DỰ LIỆU ĐÃ TRÍCH")
    print("═" * 74)
    for t in ("source_doc", "category", "series", "code_slot", "code_option",
              "part", "part_interface", "crawl_fetch", "extract_run", "review_item"):
        print(f"  {t:16} {one(f'select count(*) from {t}'):7}")

    print("\n  cache trên đĩa:", end=" ")
    n = sum(1 for _ in db.CACHE_DIR.rglob("*.*")) if db.CACHE_DIR.exists() else 0
    sz = sum(p.stat().st_size for p in db.CACHE_DIR.rglob("*.*")) if n else 0
    print(f"{n} file, {sz/1e6:.1f} MB")

    print("\n" + "═" * 74)
    print("SERIES THEO LAYER")
    print("═" * 74)
    for r in q("""select coalesce(c.layer,'(chưa gán)') layer, count(*) n
                  from series s left join category c on c.id=s.category_id
                  group by layer order by n desc"""):
        print(f"  {r['layer']:14} {r['n']:6}")

    print("\n" + "═" * 74)
    print("REVIEW QUEUE theo gợi ý ô mã")
    print("═" * 74)
    for r in q("""select json_extract(proposed,'$.slot_hint') hint,
                         state, count(*) n, round(avg(confidence),2) conf
                  from review_item group by hint, state order by n desc"""):
        print(f"  {str(r['hint']):12} {r['state']:9} {r['n']:6}  conf~{r['conf']}")

    print("\n" + "═" * 74)
    print("LỖI")
    print("═" * 74)
    rows = q("""select kind, url, last_error from crawl_target
                where state in ('failed','skipped') order by kind limit 30""")
    if not rows:
        print("  (không có)")
    for r in rows:
        print(f"  {r['kind']:12} {r['last_error'][:40]:40} {r['url'][-52:]}")

    print("\n" + "═" * 74)
    print("VÍ DỤ: series CM2 và dữ liệu quanh nó")
    print("═" * 74)
    for r in q("""select id, code, catalog_id, name, category_raw from series
                  where catalog_id like 'CM2%' or code like 'CM2%' limit 8"""):
        print(f"  #{r['id']:5} {r['code']:18} {str(r['catalog_id']):20} {str(r['name'])[:28]:28}")
    for r in q("""select json_extract(proposed,'$.slot_hint') hint,
                         json_extract(proposed,'$.code') code,
                         json_extract(proposed,'$.label') label,
                         json_extract(proposed,'$.values') vals
                  from review_item
                  where json_extract(proposed,'$.catalog_id') like 'CM2-CDM2%' limit 8"""):
        print(f"    {r['hint']:8} {str(r['code'] or r['vals'])[:16]:16} {str(r['label'] or '')[:44]}")

    con.close()


if __name__ == "__main__":
    sys.exit(main())
