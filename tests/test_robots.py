"""Kiểm bộ đọc robots.txt — crawler/robots.py.

    python3 tests/test_robots.py

VÌ SAO CÓ TỆP RIÊNG: đây là mã TUÂN THỦ. Sai một chiều thì crawler tải thứ chủ site
đã cấm, và đó là lỗi không sửa lại được bằng cách xoá dữ liệu sau.

Fixture là robots.txt THẬT của smcworld.com (tải 2026-08-26), nên test chạy offline
mà vẫn kiểm đúng thứ đã làm stdlib sai. Cả hai lỗi của urllib.robotparser đều có
test riêng ở dưới, kèm khẳng định stdlib SAI — nếu một ngày stdlib sửa được thì test
đó đỏ và ta biết là bỏ được bộ đọc riêng.
"""
import sys
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler import robots as R           # noqa: E402

UA = "PneuCompleteBot/0.1 (internal pneumatic BOM catalog; contact: tuyet@local)"
SMC = (ROOT / "tests/fixtures/robots-smcworld.txt").read_text()

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}   {detail}")


def test_smcworld_chan_dung_ba_duong_dan():
    """robots.txt thật: 3 đường dẫn bị chặn, phần còn lại cho phép."""
    g = R.parse(SMC)
    for u in ("https://www.smcworld.com/products/x/global.do",
              "https://www.smcworld.com/products/valve/ps.do",
              "https://www.smcworld.com/support/req/form",
              "https://www.smcworld.com/support/req/"):
        check(f"CHẶN {u.split('.com')[1]}", not R.allowed(g, UA, u))
    for u in ("https://www.smcworld.com/select/en-jp/",
              "https://www.smcworld.com/products/en/valve/",
              "https://www.smcworld.com/",
              # 'global.do' ở chỗ khác không khớp mẫu /products/*/global.do
              "https://www.smcworld.com/other/global.do"):
        check(f"cho phép {u.split('.com')[1] or '/'}", R.allowed(g, UA, u))


def test_stdlib_sai_hai_cho_nen_moi_co_tep_nay():
    """Khẳng định urllib.robotparser SAI trên đúng robots.txt này.

    Nếu test này đỏ thì stdlib đã sửa và bỏ được crawler/robots.py.
    """
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(SMC.splitlines())
    url = "https://www.smcworld.com/products/x/global.do"
    check("stdlib VẪN cho phép đường dẫn bị chặn (lỗi của nó)",
          rp.can_fetch(UA, url))
    check("bộ đọc của ta thì chặn", not R.allowed(R.parse(SMC), UA, url))
    # lỗi 1 riêng: hai khối `*`
    two = "User-agent: *\nAllow: /\n\nUser-agent: *\nDisallow: /secret\n"
    rp2 = urllib.robotparser.RobotFileParser()
    rp2.parse(two.splitlines())
    check("stdlib bỏ khối `*` thứ hai", rp2.can_fetch("bot", "https://x/secret"))
    check("ta GỘP hai khối `*`",
          not R.allowed(R.parse(two), "bot", "https://x/secret"))
    # lỗi 2 riêng: dấu * trong đường dẫn
    star = "User-agent: *\nDisallow: /a/*/b\n"
    rp3 = urllib.robotparser.RobotFileParser()
    rp3.parse(star.splitlines())
    check("stdlib không hiểu `*` trong đường dẫn",
          rp3.can_fetch("bot", "https://x/a/zz/b"))
    check("ta hiểu `*`", not R.allowed(R.parse(star), "bot", "https://x/a/zz/b"))


def test_nhom_cu_the_thang_nhom_sao():
    """Bot có nhóm riêng thì KHÔNG đọc nhóm `*` nữa — đúng chuẩn.

    Quan trọng cho chính chỗ này: smcworld.com chặn ClaudeBot, GPTBot, CCBot… bằng
    `Disallow: /`. Crawler của dự án khai đúng tên nó (PneuCompleteBot) nên rơi vào
    nhóm `*`; nếu bộ đọc gộp lẫn nhóm thì kết quả sai theo cả hai chiều.
    """
    g = R.parse(SMC)
    check("ClaudeBot bị chặn toàn site",
          not R.allowed(g, "ClaudeBot/1.0 (+http://anthropic.com)",
                        "https://www.smcworld.com/select/en-jp/"))
    check("GPTBot bị chặn toàn site",
          not R.allowed(g, "GPTBot/1.1", "https://www.smcworld.com/"))
    check("PneuCompleteBot theo nhóm `*` nên vào được trang thường",
          R.allowed(g, UA, "https://www.smcworld.com/select/en-jp/"))
    check("nhưng vẫn chịu 3 dòng Disallow của nhóm `*`",
          not R.allowed(g, UA, "https://www.smcworld.com/support/req/x"))


def test_luat_khop_dai_nhat_va_allow_thang_khi_bang():
    g = R.parse("User-agent: *\nDisallow: /a/\nAllow: /a/b/\n")
    check("Disallow /a/ chặn /a/x", not R.allowed(g, "b", "http://h/a/x"))
    check("Allow /a/b/ dài hơn nên mở lại nhánh con",
          R.allowed(g, "b", "http://h/a/b/c"))
    g2 = R.parse("User-agent: *\nDisallow: /x\nAllow: /x\n")
    check("dài bằng nhau thì Allow thắng", R.allowed(g2, "b", "http://h/x"))
    g3 = R.parse("User-agent: *\nDisallow:\n")
    check("`Disallow:` rỗng = cho phép tất cả", R.allowed(g3, "b", "http://h/gi-cung"))
    g4 = R.parse("User-agent: *\nDisallow: /p$\n")
    check("`$` neo cuối: /p bị chặn", not R.allowed(g4, "b", "http://h/p"))
    check("`$` neo cuối: /page KHÔNG bị chặn", R.allowed(g4, "b", "http://h/page"))
    g5 = R.parse("")
    check("robots.txt rỗng = cho phép", R.allowed(g5, "b", "http://h/x"))


def test_khong_doc_duoc_robots_thi_KHONG_phai_duoc_phep():
    """4xx = cho phép · 5xx và lỗi mạng = CHẶN.

    LỖI ĐO ĐƯỢC: fetcher.robots_ok() coi MỌI lỗi là "mặc định cho phép". Proxy trả
    403 cho mssc.smcworld.com (host chứa phần mềm chọn model) → robots_ok vẫn nói
    CHO PHÉP, tức crawler sẵn sàng tải một host mà nó CHƯA TỪNG đọc được luật.
    RFC 9309 §2.3.1: 5xx là "unavailable" và phải coi như chặn hết.
    """
    import urllib.error
    from crawler import fetcher as F

    def fake(status):
        def _g(url):
            raise urllib.error.HTTPError(url, status, "x", None, None)
        return _g

    real = F._raw_get
    try:
        for status, want_allow in ((404, True), (403, True), (500, False),
                                   (503, False)):
            F._robots.clear()
            F._raw_get = fake(status)
            got = F.robots_ok("https://vidu.test/trang")
            check(f"robots.txt trả {status} → {'cho phép' if want_allow else 'chặn'}",
                  got == want_allow, str(got))
        F._robots.clear()
        F._raw_get = lambda u: (_ for _ in ()).throw(OSError("proxy chặn"))
        check("lỗi mạng/proxy → CHẶN, không im lặng cho phép",
              not F.robots_ok("https://vidu.test/trang"))
    finally:
        F._raw_get = real
        F._robots.clear()


def test_query_string_cung_duoc_xet():
    """Mẫu có dấu ? phải khớp cả query — nếu không thì luật chặn tham số vô hiệu."""
    g = R.parse("User-agent: *\nDisallow: /s?q=\n")
    check("chặn /s?q=abc", not R.allowed(g, "b", "http://h/s?q=abc"))
    check("không chặn /s", R.allowed(g, "b", "http://h/s"))


if __name__ == "__main__":
    print("Kiểm bộ đọc robots.txt")
    print("=" * 58)
    for fn in (test_smcworld_chan_dung_ba_duong_dan,
               test_stdlib_sai_hai_cho_nen_moi_co_tep_nay,
               test_nhom_cu_the_thang_nhom_sao,
               test_luat_khop_dai_nhat_va_allow_thang_khi_bang,
               test_khong_doc_duoc_robots_thi_KHONG_phai_duoc_phep,
               test_query_string_cung_duoc_xet):
        print(f"\n{fn.__name__}")
        fn()
    print("\n" + "=" * 58)
    print(f"{ok} đạt · {fail} lỗi")
    sys.exit(1 if fail else 0)
