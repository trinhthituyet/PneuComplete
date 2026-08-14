"""Parser trang series (/webcatalog/en-jp/.../<SERIES>-E hoặc seriesList/?id=…).

Lấy được ngay từ HTML, không cần PDF (xác nhận ở docs/RECON.md §5):
  - bảng variation      Type | Series | Action | Bore size (mm)
  - Simple Specials     -XA…   Symbol | Specifications | Download
  - Made to Order       -XB/-XC…
  - link PDF catalog    → đẩy vào hàng đợi crawl, KHÔNG tải ở đây

Option của ô hậu tố (-XA/-XB/-XC) đi vào review_item chứ không ghi thẳng
code_option: chưa có code_slot vì slot chỉ dựng được từ How-to-Order trong PDF.
"""
import html as _html
import re

NAME = "html_series"
VERSION = "2"   # v2: nhận cột theo mẫu nội dung thay vì vị trí cố định

_TABLE = re.compile(r"(?is)<table.*?</table>")
_TR = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
_CELL = re.compile(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>")
_TAG = re.compile(r"(?s)<[^>]+>")

# ô bore: chỉ gồm số, dấu phẩy (cả dấu phẩy toàn phần '，'), khoảng trắng
_BORE_CELL = re.compile(r"^[\d.,，、\s]*\d[\d.,，、\s]*$")
_BORE = re.compile(r"\d+(?:\.\d+)?")
# ô mã series: chữ HOA/số/-/□, không có khoảng trắng kiểu câu chữ
_CODE_CELL = re.compile(r"^[A-Z][A-Z0-9\-/□\.]{1,24}$")
# loại nhầm: tên loại bạc đỡ, kiểu tác động... lọt vào cột series khi bảng 5 cột
_NOT_CODE = re.compile(r"(?i)bearing|bushing|acting|standard|type|precision|slide")


def _text(frag: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub(" ", frag))).strip()


def _rows(table: str):
    return [[_text(c) for c in _CELL.findall(tr)] for tr in _TR.findall(table)]


def _pick(cells):
    """Rút (series, bore_raw, action, type) từ 1 dòng bằng mẫu nội dung.

    Bảng variation của SMC có 4 hoặc 5 cột — 'Type | [Bearing] | Series | Action |
    Bore size' — và còn dùng rowspan nên số ô mỗi dòng không đều. Vì vậy nhận cột
    theo mẫu nội dung, không theo vị trí.
    """
    series = bore = action = None
    for c in cells:
        if not c:
            continue
        if bore is None and _BORE_CELL.match(c) and len(_BORE.findall(c)) >= 1:
            bore = c
        elif series is None and _CODE_CELL.match(c) and not _NOT_CODE.search(c):
            series = c
        elif action is None and re.search(r"(?i)acting", c):
            action = c
    return series, bore, action, (cells[0] if cells else None)


def parse(body: bytes, url: str):
    doc = body.decode("utf-8", "replace")
    out = {"variations": [], "suffix_options": [], "pdfs": [], "title": None}

    m = re.search(r"(?is)<title>(.*?)</title>", doc)
    if m:
        out["title"] = _text(m.group(1))

    for pdf in set(re.findall(r'href="([^"]*/catalog/[^"]*\.pdf)"', doc)):
        out["pdfs"].append(pdf if pdf.startswith("http")
                           else "https://www.smcworld.com" + pdf)

    for table in _TABLE.findall(doc):
        rows = [r for r in _rows(table) if r]
        if len(rows) < 2:
            continue
        head = " | ".join(rows[0]).lower()

        # bảng variation: Type | [Bearing] | Series | Action | Bore size (mm)
        # xuất hiện 2 lần trên trang (bảng rút gọn + bảng đầy đủ) → dedupe
        if "series" in head and "bore" in head:
            seen = {(v["series"], v["bore_raw"]) for v in out["variations"]}
            for r in rows[1:]:
                series, bore_raw, action, typ = _pick(r)
                if not series or not bore_raw:
                    continue
                key = (series, bore_raw)
                if key in seen:
                    continue
                seen.add(key)
                out["variations"].append({
                    "type": typ, "series": series, "action": action,
                    "bore_raw": bore_raw,
                    "bore_mm": [float(x) for x in _BORE.findall(bore_raw.replace("，", ","))],
                })

        # Simple Specials / Made to Order: Symbol | Specifications | Download
        elif "symbol" in head and "specification" in head:
            for r in rows[1:]:
                if len(r) < 2 or not r[0]:
                    continue
                sym = re.match(r"\s*(-?[A-Z]{1,2}\d{0,3})", r[0])
                if not sym:
                    continue
                out["suffix_options"].append({
                    "code": sym.group(1).lstrip("-"),
                    "raw_symbol": r[0],
                    "label": r[1],
                    "group": "made_to_order" if "XB" in r[0] or "XC" in r[0]
                             else "simple_special",
                })
    return out


def load(con, run_id, data, url, catalog_id, source_id=None, enqueue=None):
    """Cập nhật series + đẩy PDF vào hàng đợi + đẩy option hậu tố vào review_item."""
    from crawler import db as _db

    flagged = 0
    srow = None
    if catalog_id:
        srow = con.execute(
            "select id from series where catalog_id=?", (catalog_id,)
        ).fetchone()
    if srow is None and catalog_id:
        # series xuất hiện trong mega-menu nhưng chưa có trong indexSearch
        code = catalog_id[:-2] if catalog_id.endswith("-E") else catalog_id
        con.execute(
            """insert or ignore into series (code, catalog_id, url, source_id, notes)
               values (?,?,?,?,'discovered from mega-menu, not in indexSearch')""",
            (code.replace("-", "/"), catalog_id, url, source_id),
        )
        srow = con.execute(
            "select id from series where catalog_id=?", (catalog_id,)
        ).fetchone()
    if srow and data.get("title"):
        con.execute("update series set url=coalesce(url,?) where id=?", (url, srow["id"]))

    # bore lấy từ bảng variation → gợi ý option cho ô bore, cần PDF xác nhận thứ tự ô
    if data["variations"] and srow:
        bores = sorted({b for v in data["variations"] for b in v["bore_mm"]})
        if bores:
            _db.add_review(
                con, run_id, "code_option",
                {"series_id": srow["id"], "catalog_id": catalog_id,
                 "slot_hint": "bore", "values": bores,
                 "variations": data["variations"][:20]},
                confidence=0.7,
                note="bore lấy từ bảng variation HTML; cần How-to-Order để chốt vị trí ô",
            )
            flagged += 1

    for opt in data["suffix_options"]:
        if not srow:
            break
        _db.add_review(
            con, run_id, "code_option",
            {"series_id": srow["id"], "catalog_id": catalog_id,
             "slot_hint": "suffix", **opt},
            confidence=0.6,
            note=f"{opt['group']} từ bảng HTML; cần How-to-Order để chốt vị trí ô",
        )
        flagged += 1

    n_pdf = 0
    if enqueue:
        for pdf in data["pdfs"]:
            # PDF riêng của series (chứa How-to-Order) quan trọng hơn nhiều so với
            # PDF hướng dẫn/technical-data dùng chung cho cả catalog
            own = bool(catalog_id) and catalog_id.replace("/", "-") in pdf
            n_pdf += enqueue(con, pdf, "pdf", series_code=catalog_id,
                             priority=150 if own else 260)

    con.commit()
    return {"pdfs_queued": n_pdf, "flagged": flagged,
            "variations": len(data["variations"]),
            "suffix_options": len(data["suffix_options"])}
