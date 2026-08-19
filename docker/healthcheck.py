"""Docker HEALTHCHECK: gọi thử API xem phần mềm còn trả lời không.

Vì sao là tệp riêng chứ không viết thẳng vào HEALTHCHECK trong Dockerfile: viết
một dòng python bên trong chuỗi shell bên trong lệnh Docker là ba lớp thoát dấu
ngoặc lồng nhau — sai một dấu là healthcheck báo "unhealthy" oan mà rất khó tìm.
Tệp này chạy thử được ngay trên máy, không cần Docker.

    python3 docker/healthcheck.py     # 0 = khoẻ, 1 = không trả lời
"""
import os
import sys
import urllib.request

# Cổng lấy từ môi trường vì Dockerfile/compose đặt được PNEU_PORT.
PORT = os.environ.get("PNEU_PORT") or "8765"
# Luôn gọi 127.0.0.1: đây là kiểm tra TỪ BÊN TRONG container, không đi qua mạng.
URL = f"http://127.0.0.1:{PORT}/api/series"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=4) as r:
            if r.status != 200:
                print(f"HTTP {r.status}", file=sys.stderr)
                return 1
            # /api/series trả danh sách họ sản phẩm. Rỗng nghĩa là server sống
            # nhưng DB trống — vẫn là hỏng, chỉ báo "chạy" là che mất lỗi thật.
            body = r.read(64)
            if body.strip() in (b"", b"[]"):
                print("server trả lời nhưng DB trống", file=sys.stderr)
                return 1
        return 0
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
