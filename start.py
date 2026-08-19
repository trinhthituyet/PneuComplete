"""Khởi động PneuComplete cho người dùng cuối — tự kiểm tra, tự mở trình duyệt.

Người dùng không gõ lệnh: họ nháy đúp PneuComplete.command (macOS) hoặc
PneuComplete.bat (Windows), file đó gọi vào đây.

Việc của file này:
  · kiểm tra phiên bản Python và dữ liệu, báo lỗi bằng tiếng Việt dễ hiểu
  · tự tìm cổng còn trống (nếu 8765 đang bị dùng thì thử tiếp)
  · mở trình duyệt vào đúng địa chỉ
  · giữ cửa sổ mở và in hướng dẫn dừng
"""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

W = 68


def box(title, lines, mark="!"):
    print()
    print("┌" + "─" * W + "┐")
    print("│ " + f"{mark} {title}".ljust(W - 1) + "│")
    print("├" + "─" * W + "┤")
    for l in lines:
        for chunk in [l[i:i + W - 2] for i in range(0, max(len(l), 1), W - 2)]:
            print("│ " + chunk.ljust(W - 1) + "│")
    print("└" + "─" * W + "┘")
    print()


def die(title, lines):
    box(title, lines, mark="✗")
    print("Nhấn Enter để đóng cửa sổ này.")
    try:
        input()
    except EOFError:
        pass
    sys.exit(1)


def check_python():
    if sys.version_info < (3, 10):
        die("Phiên bản Python quá cũ", [
            f"Đang dùng Python {sys.version.split()[0]}, cần từ 3.10 trở lên.",
            "",
            "Cách sửa: tải Python mới tại python.org, cài rồi mở lại phần mềm.",
        ])


def check_data():
    # lấy đường dẫn từ crawler.db chứ không tự ghép ROOT/"pneu.db": biến môi
    # trường PNEU_DB đổi được chỗ đặt DB (Docker đặt ở /data để dữ liệu sống sót
    # qua các lần cập nhật). Ghép tay ở đây là kiểm tra sai tệp.
    from crawler import db as _db
    dbf = _db.DB_PATH
    if not dbf.exists():
        die("Thiếu tệp dữ liệu", [
            "Không tìm thấy pneu.db — đây là tệp chứa toàn bộ dữ liệu sản phẩm SMC.",
            "",
            f"Cần đặt pneu.db tại: {dbf}",
            "Nếu bạn nhận phần mềm dạng .zip, hãy giải nén TOÀN BỘ rồi chạy lại.",
        ])
    if dbf.stat().st_size < 500_000:
        die("Tệp dữ liệu có vẻ bị lỗi", [
            f"pneu.db chỉ có {dbf.stat().st_size // 1024} KB, bình thường phải vài MB.",
            "Có thể tệp bị cắt khi sao chép. Hãy lấy lại bản đầy đủ.",
        ])
    try:
        from crawler import db
        con = db.connect()
        n_series = con.execute(
            """select count(distinct series_id) n from code_slot""").fetchone()["n"]
        n_rule = con.execute("select count(*) n from rule").fetchone()["n"]
        n_cat = con.execute("select count(*) n from series").fetchone()["n"]
        con.close()
    except Exception as e:
        die("Không đọc được dữ liệu", [
            f"Lỗi: {type(e).__name__}: {e}",
            "",
            "Thường là do tệp pneu.db bị hỏng. Hãy lấy lại bản đầy đủ.",
        ])
    if n_series == 0:
        die("Dữ liệu trống", [
            "Tệp pneu.db đọc được nhưng chưa có series sản phẩm nào.",
            "Hãy lấy lại bản dữ liệu đầy đủ từ người cài đặt.",
        ])
    return n_series, n_rule, n_cat


def free_port(start=8765, tries=20):
    """Trả (cổng, None) nếu tìm được, hoặc (None, lý_do).

    Phân biệt hai nguyên nhân khác nhau — báo sai thì người dùng sửa sai chỗ:
      · EADDRINUSE : cổng đang bị chương trình khác dùng → tắt bớt là xong
      · EACCES/EPERM: hệ thống KHÔNG CHO PHÉP mở cổng (tường lửa, chính sách bảo
        mật, phần mềm diệt virus) → tắt chương trình khác không giải quyết được
    """
    import errno
    denied = False
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p, None
            except OSError as e:
                if e.errno in (errno.EACCES, errno.EPERM):
                    denied = True
                continue
    return None, ("denied" if denied else "busy")


def main():
    os.chdir(ROOT)
    print("PneuComplete — dựng danh sách vật tư khí nén")
    print("=" * (W + 2))
    check_python()
    n_series, n_rule, n_cat = check_data()
    # nói chính xác: chỉ n_series họ ĐỌC/SINH được mã, còn n_cat là toàn bộ danh
    # mục tra cứu được. Nói gộp "n_cat dòng sản phẩm" là tự phong.
    print(f"  Đọc và sinh được mã hàng cho {n_series} họ sản phẩm SMC")
    print(f"  Tra cứu được danh mục {n_cat:,} series · {n_rule} quy tắc kỹ thuật")

    port, why = free_port()
    if port is None and why == "denied":
        die("Hệ thống không cho phép mở kết nối nội bộ", [
            "Máy chặn phần mềm mở cổng kết nối trên chính máy này (localhost).",
            "Đây KHÔNG phải do cổng bị chương trình khác chiếm.",
            "",
            "Cách sửa, thử lần lượt:",
            "  1. Tường lửa / phần mềm diệt virus: cho phép Python kết nối nội bộ",
            "  2. Máy công ty có chính sách bảo mật: nhờ bộ phận IT mở quyền",
            "  3. Khởi động lại máy rồi thử lại",
        ])
    if port is None:
        die("Không mở được cổng kết nối", [
            "Đã thử từ cổng 8765 đến 8784 mà cổng nào cũng đang bị chương trình",
            "khác sử dụng.",
            "",
            "Cách sửa: tắt bớt chương trình đang chạy rồi mở lại,",
            "hoặc khởi động lại máy.",
        ])

    url = f"http://localhost:{port}"
    box("Phần mềm đang chạy", [
        f"Địa chỉ: {url}",
        "",
        "Trình duyệt sẽ tự mở sau vài giây.",
        "Nếu không tự mở, hãy sao chép địa chỉ trên vào trình duyệt.",
        "",
        "ĐỂ DỪNG: đóng cửa sổ này, hoặc nhấn Control + C.",
        "Lưu ý: đóng cửa sổ này thì trang web sẽ ngừng hoạt động.",
    ], mark="✓")

    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(url)),
                     daemon=True).start()

    try:
        from web import server
        server.main(["--port", str(port)])
    except PermissionError:
        die("Hệ thống không cho phép mở cổng kết nối", [
            "Máy đang chặn phần mềm mở kết nối nội bộ.",
            "",
            "Cách sửa: kiểm tra phần mềm diệt virus hoặc tường lửa,",
            "cho phép Python kết nối mạng nội bộ (localhost).",
        ])
    except KeyboardInterrupt:
        print("\nĐã dừng. Cảm ơn bạn.")
    except Exception as e:
        die("Phần mềm gặp lỗi không mong muốn", [
            f"{type(e).__name__}: {e}",
            "",
            "Hãy chụp ảnh cửa sổ này và gửi cho người phụ trách phần mềm.",
        ])


if __name__ == "__main__":
    main()
