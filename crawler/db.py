"""Kết nối DB + khởi tạo schema. Chỉ dùng stdlib."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "pneu.db"
CACHE_DIR = ROOT / "cache"
SCHEMA = ROOT / "db" / "schema_sqlite.sql"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    con.execute("pragma journal_mode = wal")
    return con


def init(path: Path = DB_PATH) -> sqlite3.Connection:
    con = connect(path)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.commit()
    return con


def enqueue(con, url, kind, *, series_code=None, depth=0, priority=100, parent=None):
    """Thêm URL vào hàng đợi. Trùng URL thì bỏ qua (unique constraint).

    Với kind='series': dedupe theo series_code, không theo URL. Cùng một series
    xuất hiện ở nhiều đường (URL semantic, seriesList/?id=, và nhiều category
    khác nhau) — thật tế gặp series có tới 3 URL. Crawl 1 lần là đủ.
    """
    if kind == "series" and series_code:
        dup = con.execute(
            "select 1 from crawl_target where kind='series' and series_code=? limit 1",
            (series_code,),
        ).fetchone()
        if dup:
            return 0
    cur = con.execute(
        """insert or ignore into crawl_target
           (url, kind, series_code, depth, priority, discovered_from)
           values (?,?,?,?,?,?)""",
        (url, kind, series_code, depth, priority, parent),
    )
    return cur.rowcount  # 1 = mới thêm, 0 = đã có


def next_batch(con, limit=50, kind=None):
    q = "select * from crawl_target where state='pending'"
    args = []
    if kind:
        q += " and kind=?"
        args.append(kind)
    q += " order by priority, depth, id limit ?"
    args.append(limit)
    return con.execute(q, args).fetchall()


def mark(con, target_id, state, error=None):
    con.execute(
        """update crawl_target
           set state=?, last_error=?, attempts=attempts+1,
               completed_at=case when ?='done' then datetime('now') else completed_at end
           where id=?""",
        (state, error, state, target_id),
    )


def record_fetch(con, target_id, *, status, ctype, sha, path, size, ms, source_doc_id=None):
    cur = con.execute(
        """insert into crawl_fetch
           (target_id, http_status, content_type, sha256, body_path,
            byte_size, elapsed_ms, source_doc_id)
           values (?,?,?,?,?,?,?,?)""",
        (target_id, status, ctype, sha, path, size, ms, source_doc_id),
    )
    return cur.lastrowid


def add_source_doc(con, kind, uri, sha, title=None, page_count=None):
    con.execute(
        """insert or ignore into source_doc (kind, uri, sha256, title, page_count)
           values (?,?,?,?,?)""",
        (kind, uri, sha, title, page_count),
    )
    row = con.execute(
        "select id from source_doc where uri=? and sha256 is ?", (uri, sha)
    ).fetchone()
    return row["id"] if row else None


def start_run(con, fetch_id, parser, version):
    cur = con.execute(
        """insert into extract_run (fetch_id, parser_name, parser_version)
           values (?,?,?)""",
        (fetch_id, parser, version),
    )
    return cur.lastrowid


def finish_run(con, run_id, status, rows_out=0, rows_flagged=0, log=None):
    con.execute(
        """update extract_run
           set finished_at=datetime('now'), status=?, rows_out=?, rows_flagged=?, log=?
           where id=?""",
        (status, rows_out, rows_flagged, json.dumps(log or {}, ensure_ascii=False), run_id),
    )


def add_review(con, run_id, entity_type, proposed, *, confidence=None, auto=False, note=None):
    con.execute(
        """insert into review_item
           (extract_run_id, entity_type, proposed, confidence, auto_approved, state, note)
           values (?,?,?,?,?,?,?)""",
        (
            run_id,
            entity_type,
            json.dumps(proposed, ensure_ascii=False),
            confidence,
            1 if auto else 0,
            "approved" if auto else "pending",
            note,
        ),
    )


def stats(con):
    out = {}
    q = con.execute(
        "select kind, state, count(*) n from crawl_target group by kind, state"
    ).fetchall()
    out["queue"] = {f"{r['kind']}/{r['state']}": r["n"] for r in q}
    for t in ("source_doc", "category", "series", "code_slot", "code_option",
              "part", "crawl_fetch", "extract_run", "review_item"):
        out[t] = con.execute(f"select count(*) n from {t}").fetchone()["n"]
    return out
