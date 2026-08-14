"""Khám phá URL: allowlist/denylist theo robots.txt thật + phân loại trang.

Cấu trúc URL xác nhận ở docs/RECON.md §4:
  /webcatalog/en-jp/indexSearch/<A..Z>                    index_letter
  /webcatalog/en-jp/seriesList/?id=<SERIES>-E             series (URL chuẩn)
  /webcatalog/en-jp/<cat>/                                category
  /webcatalog/en-jp/<cat>/<subcat>/                       subcategory
  /webcatalog/en-jp/<cat>/<subcat>/<SERIES>-E             series (URL semantic)
  /catalog/en/<group>/<SERIES>-E/<doc>/data/<doc>.pdf     pdf (→ ca01.smcworld.com)
"""
import re
from urllib.parse import urljoin, urlparse

BASE = "https://www.smcworld.com"

# Disallow thật trong robots.txt của SMC — loại sớm, khỏi tốn request kiểm tra
DENY = re.compile(r"^/(products/[^/]+/(global|ps)\.do|support/req/)")
ALLOW = re.compile(r"^/webcatalog/en-jp/(seriesList/|indexSearch/|[a-z0-9-]+/)")

_SERIES_TAIL = re.compile(r"/[^/]+-E$")
_PDF = re.compile(r"\.pdf($|\?)", re.I)

# ?view=picture trùng nội dung với URL gốc (đã kiểm: cùng byte_size) → bỏ.
# ?view=list thì KHÁC: trang subcategory mặc định có 0 bảng, còn view=list gộp
# bảng variation + Made-to-Order của TOÀN BỘ series trong subcategory (28 bảng
# trên 1 trang) → giữ, và đây là nguồn hiệu quả hơn fetch từng trang series.
_DUP_VIEW = re.compile(r"[?&]view=picture")


def classify(path: str) -> str | None:
    """Trả kind, hoặc None nếu không thuộc phạm vi crawl."""
    if DENY.match(path) or _DUP_VIEW.search(path):
        return None
    if _PDF.search(path):
        return "pdf" if path.startswith("/catalog/") else None
    if not path.startswith("/webcatalog/en-jp/"):
        return None
    rest = path[len("/webcatalog/en-jp/"):]
    if rest.startswith("indexSearch/"):
        return "index_letter"
    if rest.startswith("seriesList/"):
        return "series"
    depth = len([s for s in rest.split("/") if s])
    if depth == 0:
        return None                      # chính trang gốc, đã có trong seed
    if depth == 1:
        return "category"
    if depth == 2:
        return "subcategory"
    # depth >= 3 là trang series. Không phải mã nào cũng kết thúc bằng '-E':
    # gặp thật cả '…/EX260-EN', '…/EVS7-6-10', '…/VSR8/VSS8'
    return "series"


def series_id_from(url: str) -> str | None:
    """URL series → catalog_id, khớp với id trong indexSearch.

    'seriesList/?id=CM2-CDM2-Z-E'                    → 'CM2-CDM2-Z-E'
    '…/air-cylinders-round-type/CM2-CDM2-Z-E'        → 'CM2-CDM2-Z-E'
    '…/iso-valves/VSR8/VSS8'                         → 'VSR8/VSS8'
    '/catalog/en/actuator/CM2-CDM2-Z-E/…/x.pdf'      → 'CM2-CDM2-Z-E'
    """
    m = re.search(r"[?&]id=([^&]+)", url)
    if m:
        return m.group(1)
    # PDF catalog riêng của series: /catalog/en/<group>/<CATALOG_ID>/<doc>/data/<doc>.pdf
    m = re.search(r"/catalog/en/[^/]+/([^/]+)/", url)
    if m:
        return m.group(1)
    parts = [s for s in urlparse(url).path.rstrip("/").split("/") if s]
    if len(parts) >= 5 and parts[0] == "webcatalog":
        return "/".join(parts[4:])
    m = re.search(r"/([^/?#]+-E)$", url)
    return m.group(1) if m else None


def links(html: str, base_url: str):
    """Trích các link trong phạm vi, trả [(abs_url, kind, series_id)] đã lọc trùng."""
    out, seen = [], set()
    for href in re.findall(r'href="([^"]+)"', html):
        if href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absu = urljoin(base_url, href)
        p = urlparse(absu)
        if p.netloc not in ("www.smcworld.com", "ca01.smcworld.com"):
            continue
        absu = absu.split("#")[0]
        if absu in seen:
            continue
        kind = classify(p.path + (f"?{p.query}" if p.query else ""))
        if not kind:
            continue
        seen.add(absu)
        out.append((absu, kind, series_id_from(absu)))
    return out


def seed(con, enqueue):
    """Seed hàng đợi: 26 trang index A–Z + 1 trang category để lấy mega-menu."""
    n = 0
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        n += enqueue(con, f"{BASE}/webcatalog/en-jp/indexSearch/{letter}",
                     "index_letter", priority=10)
    # mega-menu của bất kỳ trang category nào cũng chứa toàn bộ cây link (RECON §3b)
    n += enqueue(con, f"{BASE}/webcatalog/en-jp/air-cylinders/", "category", priority=5)
    con.commit()
    return n
