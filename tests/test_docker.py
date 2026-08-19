"""Kiểm tra phần đóng gói Docker — chạy ĐƯỢC mà không cần Docker daemon.

VÌ SAO CÓ TỆP NÀY: tôi không build/chạy được ảnh Docker trong môi trường này
(daemon không chạy), nên không thể "thử là biết". Thay vào đó test từng mảnh
LOGIC mà lỗi ở đó sẽ làm bản Docker vỡ, và test được bằng stdlib:

  1. entrypoint.sh chép dữ liệu mẫu đúng MỘT lần — chép lần hai là xoá sạch
     phương án BOM của người dùng. Đây là lỗi tệ nhất có thể mắc.
  2. PNEU_DB/PNEU_HOST/PNEU_PORT thật sự có tác dụng — nếu không thì volume vô
     nghĩa và host không vào được container.
  3. Dockerfile/compose không tự mâu thuẫn (bind 127.0.0.1 trong container là
     lỗi kinh điển làm UI không truy cập được).
  4. .dockerignore chặn dữ liệu khách hàng và catalog có bản quyền.

    python3 tests/test_docker.py
"""
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}   {detail}")


# ---------------------------------------------------------------- entrypoint.sh
def test_entrypoint_seeds_once():
    """Lần đầu chép dữ liệu; lần sau KHÔNG được ghi đè."""
    ep = ROOT / "docker" / "entrypoint.sh"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        seed = td / "seed.db"
        seed.write_bytes(b"DU-LIEU-MAU")
        data = td / "data" / "pneu.db"
        env = {**os.environ, "PNEU_DB": str(data), "PNEU_SEED": str(seed)}

        # lần 1: /data trống → phải chép
        r1 = subprocess.run(["sh", str(ep), "true"], env=env,
                            capture_output=True, text=True)
        check("entrypoint lần 1 chạy được", r1.returncode == 0, r1.stderr[:80])
        check("entrypoint lần 1 tạo pneu.db", data.exists())
        check("entrypoint tự tạo thư mục /data", data.parent.is_dir())

        # người dùng dựng BOM → nội dung DB đổi
        data.write_bytes(b"PHUONG-AN-CUA-NGUOI-DUNG")

        # lần 2 (khởi động lại / cập nhật phiên bản): KHÔNG được chép lại
        r2 = subprocess.run(["sh", str(ep), "true"], env=env,
                            capture_output=True, text=True)
        check("entrypoint lần 2 chạy được", r2.returncode == 0, r2.stderr[:80])
        check("KHÔNG ghi đè dữ liệu người dùng khi khởi động lại",
              data.read_bytes() == b"PHUONG-AN-CUA-NGUOI-DUNG",
              f"đã bị ghi đè thành {data.read_bytes()!r}")
        check("lần 2 không in 'Lần chạy đầu'", "Lần chạy đầu" not in r2.stdout)


def test_entrypoint_runs_given_command():
    """`docker compose run app <lệnh>` phải chạy lệnh đó, không chạy server."""
    ep = ROOT / "docker" / "entrypoint.sh"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        seed = td / "seed.db"
        seed.write_bytes(b"x")
        env = {**os.environ, "PNEU_DB": str(td / "d" / "pneu.db"),
               "PNEU_SEED": str(seed)}
        r = subprocess.run(["sh", str(ep), "echo", "LENH-CUA-TOI"], env=env,
                           capture_output=True, text=True)
        check("entrypoint chạy được lệnh truyền vào",
              "LENH-CUA-TOI" in r.stdout, r.stdout[:80])


# ------------------------------------------------------------ biến môi trường
def test_pneu_db_env():
    """PNEU_DB phải đổi được chỗ đặt DB — không thì volume /data vô nghĩa."""
    code = ("import sys; sys.path.insert(0,'.')\n"
            "from crawler import db; print(db.DB_PATH)")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, text=True,
                       capture_output=True,
                       env={**os.environ, "PNEU_DB": "/data/pneu.db"})
    check("PNEU_DB đổi được đường dẫn DB",
          r.stdout.strip() == "/data/pneu.db", r.stdout.strip() or r.stderr[:80])

    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, text=True,
                       capture_output=True,
                       env={k: v for k, v in os.environ.items() if k != "PNEU_DB"})
    check("không đặt PNEU_DB thì vẫn dùng pneu.db cạnh mã nguồn",
          r.stdout.strip().endswith("PneuComplete/pneu.db"), r.stdout.strip())


def test_server_bind_env():
    """PNEU_HOST/PNEU_PORT phải tới được đúng lời gọi bind.

    Không bind thật (môi trường này chặn), chỉ thay ThreadingHTTPServer bằng bản
    giả để đọc địa chỉ nó nhận được.
    """
    code = (
        "import sys; sys.path.insert(0,'.')\n"
        "from web import server\n"
        "got = {}\n"
        "class Fake:\n"
        "    def __init__(self, addr, h): got['addr'] = addr\n"
        "    def serve_forever(self): raise KeyboardInterrupt\n"
        "server.ThreadingHTTPServer = Fake\n"
        "server.main([])\n"
        "print('ADDR', got['addr'][0], got['addr'][1])\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, text=True,
                       capture_output=True,
                       env={**os.environ, "PNEU_HOST": "0.0.0.0",
                            "PNEU_PORT": "9999"})
    check("PNEU_HOST/PNEU_PORT tới được bind()",
          "ADDR 0.0.0.0 9999" in r.stdout, r.stdout.strip() or r.stderr[-160:])

    # mặc định NGOÀI Docker phải là 127.0.0.1: bind 0.0.0.0 trên máy người dùng
    # là mở phần mềm (không có đăng nhập) cho cả mạng LAN.
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, text=True,
                       capture_output=True,
                       env={k: v for k, v in os.environ.items()
                            if k not in ("PNEU_HOST", "PNEU_PORT")})
    check("mặc định vẫn chỉ nghe 127.0.0.1:8765",
          "ADDR 127.0.0.1 8765" in r.stdout, r.stdout.strip() or r.stderr[-160:])

    # --host trên dòng lệnh phải thắng biến môi trường
    r = subprocess.run([sys.executable, "-c", code.replace(
        "server.main([])", "server.main(['--host','1.2.3.4','--port','1234'])")],
        cwd=ROOT, text=True, capture_output=True,
        env={**os.environ, "PNEU_HOST": "0.0.0.0", "PNEU_PORT": "9999"})
    check("--host/--port thắng biến môi trường",
          "ADDR 1.2.3.4 1234" in r.stdout, r.stdout.strip() or r.stderr[-160:])


# ------------------------------------------------------- Dockerfile / compose
def test_dockerfile():
    t = (ROOT / "Dockerfile").read_text()
    check("Dockerfile cài PyYAML (lý do chính dùng Docker)",
          "pyyaml" in t.lower())
    check("PyYAML ghim phiên bản (build lại ra kết quả như nhau)",
          re.search(r"pyyaml==[\d.]+", t, re.I) is not None)
    check("Dockerfile đặt PNEU_HOST=0.0.0.0",
          re.search(r"PNEU_HOST\s*=\s*0\.0\.0\.0", t) is not None)
    check("Dockerfile đặt PNEU_DB ra ngoài /app",
          "PNEU_DB=/data/pneu.db" in t)
    check("có poppler-utils (pdftotext) để thêm họ sản phẩm mới",
          "poppler-utils" in t)
    check("DB mẫu KHÔNG nằm ở /data (nếu không, volume che mất nó)",
          "/seed/pneu.db" in t and "COPY pneu.db /data" not in t)


def test_compose():
    t = (ROOT / "docker-compose.yml").read_text()
    check("compose gắn volume ./data:/data (dữ liệu sống sót khi cập nhật)",
          "./data:/data" in t)
    check("cổng chỉ mở cho máy này, không mở ra LAN",
          '"127.0.0.1:8765:8765"' in t)
    check("compose đặt PNEU_HOST 0.0.0.0",
          re.search(r"PNEU_HOST:\s*0\.0\.0\.0", t) is not None)


def test_dockerignore():
    t = (ROOT / ".dockerignore").read_text()
    lines = [l.strip() for l in t.splitlines() if l.strip() and not l.startswith("#")]
    for must in ("BOM/", "DOCUMENT/", "cache/", "data/"):
        check(f".dockerignore loại {must}", must in lines)
    check("chừa lại dist/pneu.db để build được ảnh sạch",
          "!dist/pneu.db" in lines)


def test_clean_db_option():
    """`--clean-db` phải sinh dist/pneu.db KHÔNG còn BOM khách hàng."""
    r = subprocess.run([sys.executable, "tools/package.py", "--clean-db"],
                       cwd=ROOT, capture_output=True, text=True)
    out = ROOT / "dist" / "pneu.db"
    check("tools/package.py --clean-db chạy được", r.returncode == 0,
          (r.stdout + r.stderr)[-200:])
    check("sinh ra dist/pneu.db", out.exists())
    if out.exists():
        check_db_healthy(out, "bản sạch dist/pneu.db")


def check_db_healthy(path, label):
    """Kiểm một bản DB phát hành: sạch dữ liệu khách, đủ ngữ pháp, không treo FK."""
    con = sqlite3.connect(path)
    try:
        n_bom = con.execute("select count(*) from bom_line").fetchone()[0]
        n_mach = con.execute("select count(*) from machine").fetchone()[0]
        n_series = con.execute(
            "select count(distinct series_id) from code_slot").fetchone()[0]
        integ = con.execute("pragma integrity_check").fetchone()[0]
        fk = con.execute("pragma foreign_key_check").fetchall()
    finally:
        con.close()
    check(f"{label}: KHÔNG còn BOM khách hàng", n_bom == 0 and n_mach == 0,
          f"bom_line={n_bom} machine={n_mach}")
    check(f"{label}: vẫn còn ngữ pháp sản phẩm", n_series >= 15,
          f"chỉ có {n_series} họ")
    check(f"{label}: integrity_check ok", integ == "ok", integ)
    # Từng bỏ sót: make_clean_db null `part.source_id` mà quên `series.source_id`,
    # để lại 1.296 dòng treo. Chưa vỡ ngay, nhưng nếu source_doc được nạp lại thì
    # id 1..N dùng lại → series trỏ sang TÀI LIỆU KHÁC, sai nguồn mà không báo gì.
    check(f"{label}: không còn khoá ngoại treo", not fk,
          f"{len(fk)} lỗi, ví dụ {fk[0] if fk else ''}")


def test_seed_db_committed():
    """db/seed/pneu-seed.db là thứ clone mới dựa vào — phải dùng được ngay."""
    seed = ROOT / "db" / "seed" / "pneu-seed.db"
    check("có db/seed/pneu-seed.db (clone mới lấy dữ liệu từ đây)", seed.exists())
    if not seed.exists():
        return
    mb = seed.stat().st_size / 1e6
    check("bản seed nhỏ, hợp lý để commit vào git", 0.3 < mb < 5, f"{mb:.1f} MB")
    check_db_healthy(seed, "bản seed")

    # Mỗi tệp ngữ pháp phải có mặt trong seed, nếu không thì clone mới parse
    # được ít họ hơn máy phát triển mà không ai biết.
    import glob
    try:
        import yaml
    except ModuleNotFoundError:
        return
    con = sqlite3.connect(seed)
    missing = []
    files = sorted(glob.glob(str(ROOT / "db/seed/grammar/*.yaml")))
    for f in files:
        with open(f, encoding="utf-8") as fh:
            cid = (yaml.safe_load(fh) or {}).get("series_catalog_id")
        if not cid:
            continue
        n = con.execute(
            """select count(*) from code_slot cs join series s on s.id=cs.series_id
               where s.catalog_id=?""", (cid,)).fetchone()[0]
        if n == 0:
            missing.append(f"{os.path.basename(f)}({cid})")
    con.close()
    check(f"cả {len(files)} tệp ngữ pháp đều có trong bản seed",
          not missing, ", ".join(missing))


def test_healthcheck():
    """Healthcheck phải báo HỎNG khi server không trả lời, và khi DB trống.

    Không dựng được server thật ở đây (môi trường chặn bind), nên thay urlopen
    bằng bản giả — cái cần kiểm là quy tắc phán xét, không phải mạng.
    """
    hc = ROOT / "docker" / "healthcheck.py"
    check("có docker/healthcheck.py", hc.exists())

    # server không tồn tại → 1
    r = subprocess.run([sys.executable, str(hc)], capture_output=True, text=True,
                       env={**os.environ, "PNEU_PORT": "59321"})
    check("không có server → báo hỏng (mã 1)", r.returncode == 1, str(r.returncode))

    # Nạp healthcheck.py như một module rồi thay urlopen bằng bản giả. Kiểm
    # trong cùng tiến trình cho gọn — cái cần kiểm là quy tắc phán xét.
    import importlib.util
    import urllib.request as U
    spec = importlib.util.spec_from_file_location("pneu_hc", hc)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class FakeResp:
        def __init__(self, body, status=200):
            self.body, self.status = body, status

        def read(self, n=None):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    real = U.urlopen
    try:
        for body, status, want, label in (
            (b"[]", 200, 1, "server sống nhưng DB trống → vẫn báo hỏng"),
            (b'[{"code":"CM2"}]', 200, 0, "có dữ liệu → báo khoẻ"),
            (b'[{"code":"CM2"}]', 500, 1, "HTTP 500 → báo hỏng"),
        ):
            U.urlopen = lambda *a, _b=body, _s=status, **k: FakeResp(_b, _s)
            check(label, mod.main() == want)
    finally:
        U.urlopen = real


def test_dockerfile_copies_exist():
    """Mọi đường dẫn COPY trong Dockerfile phải tồn tại, không thì build vỡ."""
    t = (ROOT / "Dockerfile").read_text()
    for m in re.finditer(r"^COPY\s+(\S+)\s+\S+\s*$", t, re.M):
        src = m.group(1)
        if src.startswith("$"):
            src = "pneu.db"          # ARG DB_FILE, mặc định
        check(f"COPY {src} — nguồn tồn tại", (ROOT / src).exists())


def test_launchers():
    for f in ("PneuComplete-Docker.command", "Tat-PneuComplete.command"):
        p = ROOT / f
        check(f"{f} tồn tại", p.exists())
        if p.exists():
            check(f"{f} có quyền chạy (nháy đúp được)",
                  os.access(p, os.X_OK))
            r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
            check(f"{f} đúng cú pháp", r.returncode == 0, r.stderr[:120])
    for f in ("PneuComplete-Docker.bat", "Tat-PneuComplete.bat"):
        check(f"{f} tồn tại", (ROOT / f).exists())

    # Quyền trong .zip: mất là macOS báo "permission denied" khi nháy đúp.
    # Kiểm HÀM đặt quyền, không kiểm tệp dist/PneuComplete.zip — tệp đó do
    # package.py tạo SAU khi chạy test này, kiểm nó là kiểm bản cũ (vòng tròn).
    import zipfile
    sys.path.insert(0, str(ROOT / "tools"))
    import package as PKG
    for name, want in (("PneuComplete-Docker.command", True),
                       ("docker/entrypoint.sh", True),
                       ("start.py", False)):
        zi = zipfile.ZipInfo(name)
        changed = PKG.set_exec_bit(zi)
        mode = zi.external_attr >> 16
        if want:
            check(f"{name} được đặt quyền chạy + bit tệp thường",
                  changed and mode & 0o111 and mode & 0o100000, oct(mode))
        else:
            check(f"{name} KHÔNG bị đặt quyền chạy (không cần)", not changed)

    mac = (ROOT / "PneuComplete-Docker.command").read_text()
    check("launcher mở rộng PATH (Finder mở .command với PATH rất hẹp)",
          "/Applications/Docker.app/Contents/Resources/bin" in mac)
    check("launcher chờ UI trả lời rồi mới mở trình duyệt",
          "/api/series" in mac)
    check("launcher nhận cả 'docker compose' và 'docker-compose'",
          "docker-compose" in mac and "docker compose" in mac)


if __name__ == "__main__":
    print("Kiểm tra đóng gói Docker")
    print("=" * 56)
    for fn in (test_entrypoint_seeds_once, test_entrypoint_runs_given_command,
               test_pneu_db_env, test_server_bind_env, test_dockerfile,
               test_dockerfile_copies_exist, test_compose, test_dockerignore,
               test_healthcheck, test_clean_db_option, test_seed_db_committed,
               test_launchers):
        print(f"\n{fn.__name__}")
        fn()
    print("\n" + "=" * 56)
    print(f"{ok} đạt · {fail} lỗi")
    sys.exit(1 if fail else 0)
