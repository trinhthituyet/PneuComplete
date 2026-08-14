"""Parser trang subcategory ?view=list.

Phát hiện lúc crawl: trang subcategory mặc định có 0 bảng, nhưng `?view=list` gộp
bảng variation + Simple Specials + Made-to-Order của TOÀN BỘ series trong
subcategory đó (ví dụ guide-cylinders: 28 bảng / 1 trang).

Khác với trang series, ở đây không có 1 catalog_id duy nhất — phải quy từng dòng
về đúng series bằng cột `Series`. Việc quy đổi này không chắc chắn 100% nên mọi
kết quả đi vào review_item, không ghi thẳng code_option.
"""
import re

from parsers import html_series

NAME = "html_subcat_list"
VERSION = "2"   # v2: nhận cột theo mẫu nội dung + đề xuất sub-series chưa có

_SPLIT = re.compile(r"[/,、･・]")
# hậu tố biến thể hay gắn sau mã series: MGPM-Z, MGP-XB24, CM2-Z1...
_VARIANT_TAIL = re.compile(r"-(?:Z\d?|X[A-Z]?\d+|XC\d+|XB\d+)$", re.I)


def build_index(con):
    """Chỉ mục tra series: mọi biến thể tên → series_id.

    series.code từ indexSearch có thể là nhóm ('MGPM/MGPL', 'CJP2/CDJP2/CJP'),
    còn bảng variation ghi từng mã một ('MGPM-Z'). Nên phải chỉ mục theo từng phần.
    """
    idx = {}
    for r in con.execute("select id, code, catalog_id from series"):
        keys = set()
        for field in (r["code"], r["catalog_id"]):
            if not field:
                continue
            base = field[:-2] if field.endswith("-E") else field
            for part in _SPLIT.split(base):
                part = part.strip().upper()
                if not part:
                    continue
                keys.add(part)
                keys.add(_VARIANT_TAIL.sub("", part))
        for k in keys:
            idx.setdefault(k, r["id"])          # trùng thì giữ series gặp trước
    return idx


def resolve(idx, token: str):
    """Mã trong bảng → series_id + độ tin cậy."""
    t = (token or "").strip().upper()
    if not t:
        return None, 0.0
    if t in idx:
        return idx[t], 0.85
    stripped = _VARIANT_TAIL.sub("", t)
    if stripped in idx:
        return idx[stripped], 0.7               # khớp sau khi bỏ hậu tố biến thể
    for part in _SPLIT.split(t):
        p = part.strip()
        if p and p in idx:
            return idx[p], 0.6
    return None, 0.0


def parse(body: bytes, url: str):
    """Dùng lại bộ trích bảng của html_series — cấu trúc bảng giống nhau."""
    return html_series.parse(body, url)


def load(con, run_id, data, url, idx):
    from crawler import db as _db

    flagged = unmatched = proposed_series = 0
    for v in data["variations"]:
        sid, conf = resolve(idx, v["series"])
        if sid is None:
            # Không phải rác: indexSearch gộp biến thể vào mã nhóm (ví dụ có
            # 'CM2/CDM2/Z' nhưng không có 'CM2K-Z'), còn bảng variation mới lộ
            # ra từng biến thể. Đề xuất thành series mới cho người duyệt.
            unmatched += 1
            _db.add_review(
                con, run_id, "series",
                {"code": v["series"], "parent_hint": _VARIANT_TAIL.sub("", v["series"].upper()),
                 "bore_mm": v["bore_mm"], "type": v["type"], "action": v["action"],
                 "source_url": url},
                confidence=0.5,
                note="biến thể series xuất hiện trong bảng variation nhưng không có "
                     "trong indexSearch — cần xác nhận là series riêng hay biến thể",
            )
            proposed_series += 1
            continue
        _db.add_review(
            con, run_id, "code_option",
            {"series_id": sid, "slot_hint": "bore", "series_token": v["series"],
             "values": v["bore_mm"], "type": v["type"], "action": v["action"],
             "source_url": url},
            confidence=round(conf * 0.9, 2),
            note="bore từ bảng variation trên trang ?view=list; cần How-to-Order "
                 "để chốt vị trí ô",
        )
        flagged += 1

    # option hậu tố trên trang này áp cho nhiều series trong subcategory —
    # không quy được về 1 series, ghi kèm URL để người duyệt tự gán
    for opt in data["suffix_options"]:
        _db.add_review(
            con, run_id, "code_option",
            {"series_id": None, "slot_hint": "suffix", "source_url": url, **opt},
            confidence=0.4,
            note="option hậu tố lấy từ trang subcategory — chưa quy được về series "
                 "cụ thể, cần người gán",
        )
        flagged += 1

    con.commit()
    return {"flagged": flagged, "unmatched": unmatched,
            "proposed_series": proposed_series,
            "variations": len(data["variations"]),
            "suffix_options": len(data["suffix_options"])}
