#!/bin/sh
# Chạy khi container khởi động.
#
# Việc chính: TÁCH dữ liệu ra khỏi mã nguồn.
#   · /seed/pneu.db  nằm TRONG ảnh Docker → mỗi lần build lại là bị thay
#   · /data/pneu.db  nằm trên volume của máy host → sống sót qua các lần cập nhật
# Lần chạy đầu, /data trống thì sao chép bản mẫu sang. Các lần sau KHÔNG chép nữa,
# nếu chép là xoá sạch phương án BOM người dùng đã dựng.
set -e

DB="${PNEU_DB:-/data/pneu.db}"
# PNEU_SEED để test được script này ngoài Docker (tests/test_docker.py).
SEED="${PNEU_SEED:-/seed/pneu.db}"
DIR=$(dirname "$DB")
mkdir -p "$DIR"

if [ ! -f "$DB" ]; then
    echo "Lần chạy đầu — sao chép dữ liệu sản phẩm SMC vào $DIR"
    cp "$SEED" "$DB"
    # WAL của SQLite cần ghi được cả tệp -wal và -shm cạnh DB, nên thư mục phải
    # ghi được, không chỉ tệp.
    chmod 664 "$DB" 2>/dev/null || true
fi

# Cảnh báo sớm nếu volume chỉ đọc: SQLite sẽ báo "attempt to write a readonly
# database" mãi về sau, lúc đó rất khó lần ra nguyên nhân.
if [ ! -w "$DIR" ]; then
    echo "CẢNH BÁO: $DIR không ghi được — sẽ không lưu được phương án BOM." >&2
    echo "  Kiểm tra lại phần volumes trong docker-compose.yml." >&2
fi

# "$@" cho phép chạy lệnh khác thay vì server, ví dụ:
#   docker compose run --rm app python3 tests/test_bom.py
#   docker compose run --rm app python3 -m engine.cli "CDM2L32-500Z x4"
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

echo "PneuComplete — dữ liệu: $DB"
exec python3 -m web.server
