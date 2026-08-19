# PneuComplete — ảnh Docker
#
# VÌ SAO DÙNG DOCKER: engine đọc cấu hình dạng YAML, cần PyYAML — thư viện KHÔNG
# có trong Python chuẩn. Chạy trực tiếp thì người dùng phải tự `pip install`.
# Docker gói sẵn PyYAML nên YAML là định dạng duy nhất, không cần bản .json song
# song, không sợ hai bản lệch nhau.
#
# Cũng gói luôn poppler-utils (lệnh pdftotext) để việc THÊM HỌ SẢN PHẨM MỚI từ
# catalog PDF chạy được trong container, không bắt người dùng cài thêm.

FROM python:3.12-slim

# pdftotext: đọc catalog PDF khi thêm họ sản phẩm mới (parsers/pdf_*.py).
# --no-install-recommends để không kéo theo cả bộ X11/font không dùng đến.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*

# PyYAML là phụ thuộc DUY NHẤT ngoài thư viện chuẩn. Ghim phiên bản để lần build
# nào cũng ra kết quả như nhau.
RUN pip install --no-cache-dir "pyyaml==6.0.2"

WORKDIR /app

# Mã nguồn và cấu hình. Thứ tự COPY đặt phần ít đổi lên trước để tận dụng cache.
COPY db/ ./db/
COPY crawler/ ./crawler/
COPY engine/ ./engine/
COPY parsers/ ./parsers/
COPY ingest/ ./ingest/
COPY web/ ./web/
COPY tests/ ./tests/
COPY docs/ ./docs/
COPY HUONG-DAN-SU-DUNG.md ./

# Dữ liệu mẫu đặt trong image ở đường dẫn KHÁC với chỗ chạy. Lúc khởi động,
# entrypoint sẽ sao chép sang /data nếu /data chưa có — nhờ vậy phương án BOM
# người dùng dựng ra nằm ở volume và KHÔNG mất khi cập nhật phiên bản.
#
# CẢNH BÁO QUAN TRỌNG — đọc trước khi build:
# Trong GÓI PHÁT HÀNH (dist/PneuComplete.zip) thì pneu.db đã được làm sạch sẵn,
# chỉ ~0,8 MB, nên build thẳng là đúng.
# Nhưng trên máy PHÁT TRIỂN, pneu.db ở thư mục gốc là bản đầy đủ (hàng trăm MB)
# và CÓ chứa BOM máy của khách hàng (bảng machine, bom_line). Build từ đó ra ảnh
# vừa nặng vừa mang dữ liệu khách hàng. Muốn gửi ảnh cho người khác:
#     python3 tools/package.py --clean-db
#     docker build --build-arg DB_FILE=dist/pneu.db -t pneucomplete .
ARG DB_FILE=pneu.db
COPY ${DB_FILE} /seed/pneu.db

COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/healthcheck.py /healthcheck.py
RUN chmod +x /entrypoint.sh

# Trong container PHẢI bind 0.0.0.0. Bind 127.0.0.1 chỉ nghe loopback CỦA
# container nên máy host không vào được — lỗi rất dễ mắc.
ENV PNEU_HOST=0.0.0.0 \
    PNEU_PORT=8765 \
    PNEU_DB=/data/pneu.db \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8765
VOLUME ["/data"]

# Logic để trong docker/healthcheck.py — chạy thử được ngoài Docker, và tránh
# ba lớp thoát dấu ngoặc lồng nhau nếu viết một dòng ngay tại đây.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD ["python3", "/healthcheck.py"]

ENTRYPOINT ["/entrypoint.sh"]
