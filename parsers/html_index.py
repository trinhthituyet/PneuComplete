"""Parser trang /webcatalog/en-jp/indexSearch/<A..Z>.

Đây là nguồn seed cho bảng `series`: bảng HTML sạch với 5 cột
  Category | Product name | Series | Type | Detail(link seriesList/?id=…)
Xác nhận ở docs/RECON.md §3a — riêng chữ C có 361 dòng.
"""
import html as _html
import re

NAME = "html_index"
VERSION = "1"

_TR = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
_CELL = re.compile(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>")
_TAG = re.compile(r"(?s)<[^>]+>")

# ánh xạ category gốc của SMC → layer trong schema
LAYER = [
    (r"air cylinder|actuator|gripper|rotary|slide|clamp", "actuator"),
    (r"valve", "valve"),
    (r"air preparation|filter|regulator|lubricator|dryer|air prep", "air_prep"),
    (r"fitting|tubing|tube", "piping"),
    (r"switch|sensor|controller|ionizer|counter", "electrical"),
    (r"speed controller|flow control|silencer|exhaust", "accessory"),
]


def _text(frag: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub(" ", frag))).strip()


def layer_of(category_raw: str) -> str:
    low = category_raw.lower()
    for pat, layer in LAYER:
        if re.search(pat, low):
            return layer
    return "other"


def parse(body: bytes):
    """Trả list dict: {category_raw, name, code, type, catalog_id, url}."""
    doc = body.decode("utf-8", "replace")
    rows = []
    for tr in _TR.findall(doc):
        cells = [_text(c) for c in _CELL.findall(tr)]
        if len(cells) < 4:
            continue
        cat, name, code, typ = cells[0], cells[1], cells[2], cells[3]
        if not code or cat.lower() == "category":       # bỏ dòng header
            continue
        m = re.search(r'href="([^"]*seriesList/\?id=([^"&]+))"', tr)
        rows.append({
            "category_raw": cat,
            "name": name,
            "code": code,
            "type": typ,
            "catalog_id": m.group(2) if m else None,
            "url": ("https://www.smcworld.com" + m.group(1)) if m else None,
        })
    return rows


def load(con, run_id, rows, source_id=None):
    """Ghi vào category + series. is_verified để dành cho part, series ghi trực tiếp
    vì đây là bảng HTML có cấu trúc rõ — nhưng vẫn ghi source_id để truy nguồn."""
    n_series = n_cat = 0
    for r in rows:
        cat_code = re.sub(r"[^a-z0-9]+", "-", r["category_raw"].lower()).strip("-")[:120]
        if not cat_code:
            continue
        cur = con.execute(
            "insert or ignore into category (code, name, layer) values (?,?,?)",
            (cat_code, r["category_raw"], layer_of(r["category_raw"])),
        )
        n_cat += cur.rowcount
        cat = con.execute("select id from category where code=?", (cat_code,)).fetchone()
        cur = con.execute(
            """insert or ignore into series
               (code, catalog_id, name, category_id, category_raw, url, source_id)
               values (?,?,?,?,?,?,?)""",
            (r["code"], r["catalog_id"], r["name"], cat["id"],
             r["category_raw"], r["url"], source_id),
        )
        n_series += cur.rowcount
    con.commit()
    return n_series, n_cat
