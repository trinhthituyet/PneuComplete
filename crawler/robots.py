"""Đọc robots.txt cho đúng — thay urllib.robotparser vì nó sai HAI chỗ.

    python3 -m crawler.robots https://www.smcworld.com/products/x/global.do

VÌ SAO KHÔNG DÙNG STDLIB: đo trên robots.txt thật của smcworld.com, cả hai lỗi đều
làm crawler tưởng ĐƯỢC PHÉP những đường dẫn chủ site đã CHẶN.

LỖI 1 — BỎ KHỐI `User-agent: *` THỨ HAI.
  CPython urllib/robotparser.py, _add_entry():
      if "*" in entry.useragents:
          if self.default_entry is None:      # "the first default entry wins"
              self.default_entry = entry
  robots.txt của smcworld.com có HAI khối `*`: một do Cloudflare chèn (Allow: /) và
  một của chính SMC (ba dòng Disallow). Khối thứ hai bị bỏ HẲN.
  Kiểu "một khối do CDN chèn + một khối của chủ site" giờ rất phổ biến, nên đây là
  lỗi sẽ gặp lại ở host khác, không phải chuyện riêng của một trang.

LỖI 2 — URL-ENCODE DẤU `*` TRONG ĐƯỜNG DẪN.
  Gộp xong hai khối rồi vẫn không chặn được, vì stdlib đổi
  `/products/*/global.do` thành `/products/%2A/global.do`. Dấu `*` là phần mở rộng
  của Google, không có trong RFC gốc, và stdlib không hỗ trợ. Mọi luật có `*` trở
  thành vô hiệu một cách IM LẶNG.

ĐO ĐƯỢC TRÊN DB: 0/2718 URL đã tải thuộc đường dẫn bị chặn — nên chưa từng vi
phạm. Nhưng đó là may, không phải do luật đang chạy đúng.

── LUẬT ÁP DỤNG ─────────────────────────────────────────────────────────────
· Nhóm khớp User-agent CỤ THỂ (khớp tiền tố, không phân biệt hoa thường) thắng
  nhóm `*`. Đúng chuẩn: bot có nhóm riêng thì KHÔNG đọc nhóm `*` nữa.
· Trong một nhóm: luật có ĐƯỜNG DẪN DÀI NHẤT khớp sẽ thắng; bằng nhau thì Allow
  thắng (quy ước của Google, và là hướng THẬN TRỌNG với chủ site vì họ dùng Allow
  để mở lại một nhánh con bên trong vùng đã Disallow).
· `Disallow:` để trống nghĩa là cho phép tất cả — không phải chặn tất cả.
· Không lấy được robots.txt: 4xx = không có tệp → cho phép (RFC 9309 §2.3.1);
  5xx hoặc lỗi mạng/proxy = KHÔNG BIẾT luật → chặn hết (DENY_ALL).
· `*` khớp chuỗi bất kỳ, `$` neo cuối đường dẫn.
"""
import re
import sys
import urllib.parse


# Nhóm luật "chặn hết", dùng khi KHÔNG đọc được robots.txt (5xx, mạng lỗi, proxy
# chặn). Không đọc được luật thì không phải là được phép — xem fetcher.robots_ok.
DENY_ALL = {"*": [(False, "/")]}


def parse(text):
    """robots.txt → {user-agent chữ thường: [(cho_phép, đường_dẫn), …]}.

    GỘP các khối trùng user-agent thay vì bỏ khối sau — đây là lỗi 1 ở docstring.
    """
    groups, cur = {}, []
    expect_ua = True
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if not expect_ua:            # dòng UA sau các luật → bắt đầu nhóm mới
                cur = []
            expect_ua = True
            cur.append(groups.setdefault(value.lower(), []))
        elif field in ("allow", "disallow"):
            expect_ua = False
            if field == "disallow" and value == "":
                continue                 # 'Disallow:' rỗng = cho phép tất cả
            for g in cur:
                g.append((field == "allow", value))
        # Content-Signal, Crawl-delay, Sitemap…: không thuộc phần cho/không cho
    return groups


def rules_for(groups, ua):
    """Nhóm luật áp dụng cho ua. Nhóm CỤ THỂ thắng `*`, không cộng gộp hai nhóm."""
    ua = (ua or "").lower()
    best, best_len = None, -1
    for key, rules in groups.items():
        if key == "*":
            continue
        # khớp tiền tố: 'ClaudeBot' khớp UA 'claudebot/1.0 (+http…)'
        token = key.split("/")[0]
        if token and token in ua and len(token) > best_len:
            best, best_len = rules, len(token)
    return best if best is not None else groups.get("*", [])


def path_match(pattern, path):
    """Khớp đường dẫn robots: `*` = chuỗi bất kỳ, `$` ở cuối = neo hết đường dẫn."""
    if not pattern:
        return False
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern)
    return re.match(rx + ("$" if anchored else ""), path) is not None


def allowed(groups, ua, url):
    """Có được tải url không? Không có luật nào khớp → cho phép (mặc định của chuẩn)."""
    p = urllib.parse.urlsplit(url)
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    win, win_len = True, -1
    for allow, pat in rules_for(groups, ua):
        if not path_match(pat, path):
            continue
        n = len(pat)
        # dài hơn thì thắng; DÀI BẰNG NHAU thì Allow thắng
        if n > win_len or (n == win_len and allow):
            win, win_len = allow, n
    return win


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    import urllib.request
    from . import fetcher
    p = urllib.parse.urlsplit(argv[0])
    req = urllib.request.Request(f"{p.scheme}://{p.netloc}/robots.txt",
                                 headers={"User-Agent": fetcher.UA})
    txt = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    g = parse(txt)
    print(f"{len(g)} nhóm user-agent: {', '.join(sorted(g))}")
    for u in argv:
        print(f"  {'CHO PHÉP' if allowed(g, fetcher.UA, u) else 'CHẶN   '}  {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
