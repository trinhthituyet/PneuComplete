"""Đóng gói PneuComplete gửi cho người dùng cuối.

    python3 tools/package.py              → dist/PneuComplete.zip
    python3 tools/package.py --check      → chỉ kiểm tra, không tạo tệp
    python3 tools/package.py --clean-db   → chỉ sinh dist/pneu.db đã làm sạch
                                            (để build ảnh Docker gửi ra ngoài)
    python3 tools/package.py --json-only  → sinh .json cấu hình, cho máy KHÔNG
                                            có Docker lẫn PyYAML

CÁCH GIAO HÀNG CHÍNH LÀ DOCKER (xem HUONG-DAN-SU-DUNG.md): ảnh Docker đã có
PyYAML nên tệp cấu hình giữ nguyên dạng .yaml — một bản duy nhất, không sợ bản
.json lệch với bản .yaml. Gói .zip này vẫn giữ làm phương án cho máy không cài
được Docker; lúc đó mới cần --json-only.

Nguyên tắc: gói CHỈ những gì cần để chạy UI. Không gói:
  · cache/    ~950 MB HTML/PDF thô — chỉ cần khi crawl lại
  · DOCUMENT/ ~400 MB catalog PDF — có bản quyền SMC, KHÔNG phát hành lại
  · BOM/      dữ liệu khách hàng — không gửi cho người khác
  · pdfs/     symlink vào cache
  · *.bak, .git, __pycache__, log

Trước khi đóng gói, script tự KIỂM TRA phần mềm còn chạy được: chạy bộ test và
thử dựng một BOM mẫu. Gói một bản hỏng rồi gửi đi là tệ hơn không gói.
"""
import pathlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Thư mục/tệp cần có trong gói
INCLUDE_DIRS = ["crawler", "engine", "parsers", "ingest", "web", "db", "tests"]
INCLUDE_FILES = [
    "start.py", "PneuComplete.command", "PneuComplete.bat",
    "PneuComplete-Docker.command", "PneuComplete-Docker.bat",
    "Tat-PneuComplete.command", "Tat-PneuComplete.bat",
    "Dockerfile", "docker-compose.yml", ".dockerignore",
    "docker/entrypoint.sh", "docker/healthcheck.py",
    "HUONG-DAN-SU-DUNG.md", "pneu.db",
]
INCLUDE_DOCS = ["docs/DESIGN.md", "docs/RECON.md", "docs/CRAWL-RESULTS.md",
                "docs/ROADMAP.md"]

EXCLUDE_PARTS = {"__pycache__", ".git", ".DS_Store", "cache", "DOCUMENT",
                 "BOM", "pdfs", "dist"}
EXCLUDE_SUFFIX = {".pyc", ".bak", ".log", ".tmp"}


def keep(p: Path) -> bool:
    if any(part in EXCLUDE_PARTS for part in p.parts):
        return False
    if p.suffix in EXCLUDE_SUFFIX:
        return False
    return True


def gen_json():
    """Sinh .json cạnh mỗi .yaml cấu hình.

    Bản phát hành đọc .json bằng stdlib nên KHÔNG cần PyYAML. Nếu bỏ bước này,
    phần mềm vỡ trên máy người dùng với ModuleNotFoundError: No module named 'yaml'.
    """
    import glob
    sys.path.insert(0, str(ROOT))
    from engine import conf
    made = []
    for f in sorted(glob.glob(str(ROOT / "db/seed/**/*.yaml"), recursive=True)):
        made.append(conf.dump_json(f))
    return made


def check_no_deps():
    """Xác nhận bản phát hành chạy được khi máy KHÔNG có thư viện ngoài stdlib.

    Giả lập bằng cách chặn `import yaml` rồi dựng thử một BOM. Đây là bài kiểm tra
    mà tôi đã bỏ sót lần đầu: tôi tưởng project chỉ dùng stdlib, thực ra PyYAML
    nằm ngay trên đường chạy chính của UI.
    """
    code = (
        "import sys, builtins\n"
        "real = builtins.__import__\n"
        "def fake(n, *a, **k):\n"
        "    if n == 'yaml': raise ModuleNotFoundError(\"No module named 'yaml'\")\n"
        "    return real(n, *a, **k)\n"
        "builtins.__import__ = fake\n"
        "sys.path.insert(0, '.')\n"
        "from crawler import db\n"
        "from engine import bom\n"
        "con = db.connect(); bom.seed_rules(con)\n"
        "r = bom.build(con, [('CDM2L32-500Z', 5, {'valve_function': 'double'})],\n"
        "              {'tube_total_m': 60, 'valve_series_size': 'SY5000'})\n"
        "assert len(r['lines']) >= 4, r['lines']\n"
        "print('ok', len(r['lines']))\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                       capture_output=True, text=True)
    ok = r.returncode == 0
    msg = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or [""]
    print(f"  {'✓' if ok else '✗'} chạy không cần PyYAML     {msg[0][:44]}")
    return [] if ok else ["cần PyYAML mới chạy được — thiếu tệp .json?"]


def run_checks(json_mode=False):
    """Không đóng gói bản hỏng: chạy test + dựng thử một BOM."""
    problems = []
    for t in ("tests/test_parser.py", "tests/test_bom.py", "tests/test_web.py",
              "tests/test_graph.py", "tests/test_robots.py", "tests/test_docker.py"):
        r = subprocess.run([sys.executable, t], cwd=ROOT,
                           capture_output=True, text=True)
        tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
        ok = r.returncode == 0
        print(f"  {'✓' if ok else '✗'} {t:26} {tail[0]}")
        if not ok:
            problems.append(t)

    # test hình học canvas cần node. Node KHÔNG phải phụ thuộc của phần mềm —
    # nó chỉ dùng để kiểm tệp .js lúc phát triển. Máy không có node thì bỏ qua và
    # NÓI RÕ là đã bỏ qua, không im lặng coi như đạt.
    if shutil.which("node"):
        r = subprocess.run(["node", "tests/test_ui.js"], cwd=ROOT,
                           capture_output=True, text=True)
        tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
        print(f"  {'✓' if r.returncode == 0 else '✗'} tests/test_ui.js         {tail[0]}")
        if r.returncode != 0:
            problems.append("tests/test_ui.js")
    else:
        print("  · tests/test_ui.js         BỎ QUA (máy không có node)")

    # dựng thử BOM để chắc engine còn chạy với dữ liệu trong pneu.db
    try:
        from crawler import db
        from engine import bom
        con = db.connect()
        bom.seed_rules(con)
        res = bom.build(con, [("CDM2L32-500Z", 5, {"valve_function": "double"})],
                        {"tube_total_m": 60, "valve_series_size": "SY5000"},
                        project_name="package-check")
        con.close()
        n = len(res["lines"])
        print(f"  {'✓' if n >= 4 else '✗'} dựng BOM mẫu              {n} dòng")
        if n < 4:
            problems.append("BOM mẫu ra quá ít dòng")
    except Exception as e:
        print(f"  ✗ dựng BOM mẫu              {type(e).__name__}: {e}")
        problems.append("dựng BOM mẫu lỗi")

    # Chỉ kiểm tra "chạy được khi không có PyYAML" khi thật sự làm bản .zip —
    # bản Docker luôn có PyYAML nên phép thử này không nói lên điều gì.
    if json_mode:
        problems += check_no_deps()

    dbf = ROOT / "pneu.db"
    mb = dbf.stat().st_size / 1e6 if dbf.exists() else 0
    print(f"  {'✓' if mb > 0.5 else '✗'} pneu.db                   {mb:.1f} MB")
    if mb <= 0.5:
        problems.append("pneu.db thiếu hoặc quá nhỏ")
    return problems


# Bảng KHÔNG đưa vào bản phát hành, và lý do:
#   machine, bom_line        → BOM máy của KHÁCH HÀNG. Tuyệt đối không gửi cho
#                              người khác. Đây là lý do quan trọng nhất.
#   project*                 → phương án đã dựng, gồm cả rác từ test (5.495 dòng)
#   crawl_*, extract_run,
#   review_item, source_doc  → dấu vết crawl và hàng đợi duyệt, chỉ cần khi CẬP
#                              NHẬT catalog. Người dùng cuối không cần, mà chúng
#                              chiếm phần lớn dung lượng.
STRIP_TABLES = [
    "machine", "bom_line", "cooccurrence",
    # project_graph phải nằm ở ĐÂY, không chỉ dựa vào on-delete-cascade:
    # make_clean_db chạy với `pragma foreign_keys = off` nên cascade KHÔNG bắn,
    # sẽ để lại sơ đồ mồ côi và chốt foreign_key_check sẽ chặn việc đóng gói.
    "project_graph",
    "project_output", "project_warning", "project_input", "project",
    "crawl_fetch", "crawl_target", "extract_run", "review_item", "source_doc",
    "a3_decision",
]


def make_clean_db(src: pathlib.Path, dst: pathlib.Path):
    """Tạo bản pneu.db sạch để phát hành. Trả (mb_trước, mb_sau, số_dòng_đã_xoá)."""
    import sqlite3
    if dst.exists():
        dst.unlink()
    shutil.copy2(src, dst)
    con = sqlite3.connect(dst)
    con.execute("pragma foreign_keys = off")
    removed = 0
    for t in STRIP_TABLES:
        try:
            n = con.execute(f"select count(*) from {t}").fetchone()[0]
            con.execute(f"delete from {t}")
            removed += n
        except sqlite3.OperationalError:
            pass          # bảng không tồn tại trong bản này

    # Gỡ MỌI tham chiếu treo tới bảng vừa xoá — quét khoá ngoại chứ không vá tay
    # từng cột. Trước đây chỉ null `part.source_id` mà bỏ sót `series.source_id`,
    # để lại 1.296 dòng treo.
    #
    # Vì sao phải gỡ, dù SELECT vẫn chạy bình thường: nếu sau này source_doc được
    # nạp lại, id 1..N sẽ được dùng lại và những dòng treo này bỗng trỏ sang TÀI
    # LIỆU KHÁC — sai nguồn tra cứu mà không có lỗi nào báo ra.
    keep = [r[0] for r in con.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%'")
        if r[0] not in STRIP_TABLES]
    for t in keep:
        for fk in con.execute(f"pragma foreign_key_list({t})").fetchall():
            target, col = fk[2], fk[3]
            if target in STRIP_TABLES and col:
                con.execute(f"update {t} set {col}=null where {col} is not null")

    con.commit()
    con.execute("vacuum")

    # Không phát hành DB còn lỗi khoá ngoại: người sau chạy pragma
    # foreign_key_check sẽ thấy DB hỏng và không biết vì sao.
    bad = con.execute("pragma foreign_key_check").fetchall()
    con.close()
    if bad:
        raise RuntimeError(
            f"DB sạch còn {len(bad)} lỗi khoá ngoại — kiểm lại STRIP_TABLES. "
            f"Ví dụ: {bad[0]}")
    return src.stat().st_size / 1e6, dst.stat().st_size / 1e6, removed


def set_exec_bit(zi):
    """Đặt quyền thực thi cho .command/.sh bên trong .zip.

    Không có quyền này thì macOS báo "permission denied" khi người dùng nháy đúp
    — mà lỗi đó chỉ hiện ra trên máy người dùng, không hiện lúc mình đóng gói.

    Phải là 0o100755, KHÔNG phải 0o755: 0o100000 là bit "tệp thường" của POSIX.
    Thiếu nó, một số công cụ giải nén hiểu entry là kiểu tệp khác.

    Trả True nếu có sửa (để test kiểm được).
    """
    if zi.filename.endswith((".command", ".sh")):
        zi.external_attr = 0o100755 << 16
        return True
    return False


def collect():
    files = []
    for d in INCLUDE_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and keep(p):
                files.append(p)
    for f in INCLUDE_FILES + INCLUDE_DOCS:
        p = ROOT / f
        if p.is_file():
            files.append(p)
        elif f != "pneu.db":
            print(f"  ⚠ thiếu {f}")
    return files


def main(argv):
    print("PneuComplete — đóng gói")
    print("=" * 56)

    # --clean-db xử lý TRƯỚC bộ kiểm tra, và có lý do bắt buộc phải vậy:
    # run_checks() chạy tests/test_docker.py, mà test đó gọi lại chính lệnh
    # `--clean-db` để kiểm tra bản DB sạch. Đặt sau run_checks() là đệ quy vô
    # tận (đã mắc một lần). Bước này cũng không cần test: nó chỉ xoá bảng.
    if "--clean-db" in argv:
        # dùng khi build ảnh Docker để GỬI RA NGOÀI:
        #   docker build --build-arg DB_FILE=dist/pneu.db -t pneucomplete .
        (ROOT / "dist").mkdir(exist_ok=True)
        before, after, removed = make_clean_db(ROOT / "pneu.db",
                                               ROOT / "dist" / "pneu.db")
        print(f"\n✓ dist/pneu.db — xoá {removed:,} dòng "
              f"(BOM khách hàng, phương án test, dấu vết crawl)")
        print(f"  {before:.1f} MB → {after:.1f} MB")
        return 0

    # Chỉ sinh .json khi được yêu cầu. Cách giao hàng chính là Docker (có
    # PyYAML) nên .yaml là bản duy nhất; sinh .json mặc định là tạo ra bản thứ
    # hai dễ lệch với bản gốc.
    if "--json-only" in argv or "--zip" in argv:
        made = gen_json()
        print(f"Sinh {len(made)} tệp .json cấu hình (cho máy không có PyYAML)")
    print("\nKiểm tra trước khi gói:")
    problems = run_checks(json_mode="--json-only" in argv or "--zip" in argv)
    if problems:
        print(f"\n✗ KHÔNG đóng gói: {len(problems)} vấn đề — {', '.join(problems)}")
        print("  Sửa xong rồi chạy lại.")
        return 1
    if "--json-only" in argv:
        print("\n✓ Đã sinh xong .json (không tạo gói).")
        return 0
    if "--check" in argv:
        print("\n✓ Mọi kiểm tra đều đạt (chỉ kiểm tra, không tạo tệp).")
        return 0

    # làm sạch DB trước khi gói
    clean = ROOT / "dist" / "pneu.db"
    (ROOT / "dist").mkdir(exist_ok=True)
    before, after, removed = make_clean_db(ROOT / "pneu.db", clean)
    print(f"\nLàm sạch dữ liệu phát hành:")
    print(f"  xoá {removed:,} dòng (BOM khách hàng, phương án test, dấu vết crawl)")
    print(f"  {before:.1f} MB → {after:.1f} MB")

    files = collect()
    total = sum(f.stat().st_size for f in files)
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    # tên tệp không dùng ngày giờ tự sinh (không lấy được trong môi trường này)
    out = dist / "PneuComplete.zip"
    if out.exists():
        out.unlink()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            if f.name == "pneu.db" and f.parent == ROOT:
                continue                      # dùng bản đã làm sạch bên dưới
            rel = Path("PneuComplete") / f.relative_to(ROOT)
            z.write(f, rel)
        z.write(clean, Path("PneuComplete") / "pneu.db")
        for zi in z.infolist():
            set_exec_bit(zi)

    print(f"\n✓ Đã tạo {out.relative_to(ROOT)}")
    print(f"  {len(files)} tệp · {total/1e6:.1f} MB gốc → {out.stat().st_size/1e6:.1f} MB nén")
    print("\nGửi tệp .zip này cho người dùng. Họ giải nén TOÀN BỘ, rồi:")
    print("  · Cách chuẩn (khuyến nghị) — cần Docker Desktop:")
    print("      nháy đúp PneuComplete-Docker.command / .bat")
    print("      → không phải cài Python, không phải cài thư viện")
    print("  · Máy không cài được Docker — cần Python 3.10+ và PyYAML:")
    print("      nháy đúp PneuComplete.command / .bat")
    if "--json-only" in argv or "--zip" in argv:
        print("      (gói này đã kèm .json nên kh��ng cần PyYAML)")
    else:
        print("      LƯU Ý: gói này KHÔNG kèm .json. Muốn chạy không cần PyYAML")
        print("      thì đóng gói lại bằng: python3 tools/package.py --zip")
    print("\nĐã LOẠI khỏi gói (cố ý):")
    print("  · DOCUMENT/  catalog PDF của SMC — có bản quyền, không phát hành lại")
    print("  · BOM/       tệp Excel BOM khách hàng")
    print("  · trong pneu.db: bảng machine/bom_line (BOM khách hàng), project* (test),")
    print("    crawl_*/review_item (dấu vết crawl, chỉ cần khi cập nhật catalog)")
    print("  · cache/     ~950 MB dữ liệu crawl thô, chỉ cần khi cập nhật catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
