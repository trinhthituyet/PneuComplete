"""Tầng 1 của crawler: chỉ tải và lưu nguyên trạng. Không parse gì ở đây.

Quy tắc bắt buộc (docs/DESIGN.md §4.6):
  - tuân robots.txt, kiểm tra trước mỗi URL, cache theo host
  - <= 1 request/giây, đồng thời = 1 cho mỗi host
  - backoff luỹ thừa + jitter khi 429/5xx, tôn trọng Retry-After
  - User-Agent khai đúng danh tính, không giả dạng trình duyệt
"""
import gzip
import hashlib
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

from . import db

UA = "PneuCompleteBot/0.1 (internal pneumatic BOM catalog; contact: tuyet@local)"
MIN_INTERVAL = 1.0        # giây giữa 2 request cùng host
MAX_ATTEMPTS = 3
TIMEOUT = 90

_last_hit: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser] = {}


class Blocked(Exception):
    """robots.txt không cho phép."""


def _throttle(host: str) -> None:
    now = time.monotonic()
    wait = MIN_INTERVAL - (now - _last_hit.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


def _raw_get(url: str) -> tuple[int, str, bytes, int]:
    """GET thô, có giải nén gzip. Trả (status, content_type, body, elapsed_ms)."""
    host = urlparse(url).netloc
    _throttle(host)
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Encoding": "gzip", "Accept": "*/*"}
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        ms = int((time.monotonic() - t0) * 1000)
        return resp.status, resp.headers.get("Content-Type", ""), body, ms


def robots_ok(url: str) -> bool:
    """Kiểm tra robots.txt của host, cache kết quả parser theo host."""
    p = urlparse(url)
    host = p.netloc
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            _, _, body, _ = _raw_get(f"{p.scheme}://{host}/robots.txt")
            rp.parse(body.decode("utf-8", "replace").splitlines())
        except Exception:
            rp.allow_all = True     # không lấy được robots.txt → mặc định cho phép
        _robots[host] = rp
    return _robots[host].can_fetch(UA, url)


def cache_path(sha: str, ext: str) -> Path:
    d = db.CACHE_DIR / sha[:2]
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sha}{ext}"


def _ext_for(ctype: str) -> str:
    if "pdf" in ctype:
        return ".pdf"
    if "json" in ctype:
        return ".json"
    if "html" in ctype:
        return ".html"
    return ".bin"


def fetch(con, target) -> dict | None:
    """Tải 1 target, lưu vào cache + crawl_fetch. Trả dict kết quả, hoặc None nếu bỏ.

    Idempotent theo nội dung: sha256 đã có trong cache thì không ghi lại file.
    """
    url = target["url"]
    if not robots_ok(url):
        con.execute("update crawl_target set robots_allowed=0 where id=?", (target["id"],))
        db.mark(con, target["id"], "skipped", "robots.txt disallow")
        con.commit()
        return None
    con.execute("update crawl_target set robots_allowed=1 where id=?", (target["id"],))

    delay = 2.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            status, ctype, body, ms = _raw_get(url)
            sha = hashlib.sha256(body).hexdigest()
            path = cache_path(sha, _ext_for(ctype))
            fresh = not path.exists()
            if fresh:
                path.write_bytes(body)

            src_kind = "pdf" if "pdf" in ctype else "web"
            src_id = db.add_source_doc(con, src_kind, url, sha)
            fid = db.record_fetch(
                con, target["id"], status=status, ctype=ctype, sha=sha,
                path=str(path.relative_to(db.ROOT)), size=len(body), ms=ms,
                source_doc_id=src_id,
            )
            db.mark(con, target["id"], "done")
            con.commit()
            return {"fetch_id": fid, "sha": sha, "path": path, "body": body,
                    "status": status, "ctype": ctype, "fresh_bytes": fresh, "ms": ms}

        except urllib.error.HTTPError as e:
            retryable = e.code == 429 or 500 <= e.code < 600
            if retryable and attempt < MAX_ATTEMPTS:
                ra = e.headers.get("Retry-After") if e.headers else None
                sleep_s = float(ra) if (ra or "").isdigit() else delay + (attempt * 0.37)
                time.sleep(sleep_s)
                delay *= 2
                continue
            db.mark(con, target["id"], "failed", f"HTTP {e.code}")
            con.commit()
            return None

        except Exception as e:                      # timeout, DNS, reset...
            if attempt < MAX_ATTEMPTS:
                time.sleep(delay + attempt * 0.37)
                delay *= 2
                continue
            db.mark(con, target["id"], "failed", f"{type(e).__name__}: {e}"[:300])
            con.commit()
            return None
