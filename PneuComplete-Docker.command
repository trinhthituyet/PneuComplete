#!/bin/bash
# PneuComplete — mở phần mềm bằng Docker (macOS)
#
# Nháy đúp tệp này. Không cần cài Python, không cần cài thư viện.
#
# Lần đầu chạy sẽ LÂU (5–15 phút) vì Docker phải tải và dựng ảnh. Từ lần thứ hai
# chỉ mất vài giây.

cd "$(dirname "$0")" || exit 1

PORT=8765
URL="http://localhost:$PORT"

# Finder mở .command với PATH rất hẹp, thường KHÔNG có docker. Bổ sung các chỗ
# Docker Desktop và Homebrew thường đặt lệnh docker.
export PATH="$PATH:/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$HOME/.docker/bin"

W=68
box() {  # box "TIÊU ĐỀ"  rồi các dòng nội dung qua stdin
    echo
    printf '┌%*s┐\n' $W '' | tr ' ' '─'
    printf '│ %-*s│\n' $((W-1)) "$1"
    printf '├%*s┤\n' $W '' | tr ' ' '─'
    while IFS= read -r l; do printf '│ %-*s│\n' $((W-1)) "$l"; done
    printf '└%*s┘\n' $W '' | tr ' ' '─'
    echo
}

hold() { echo; echo "Nhấn Enter để đóng cửa sổ này."; read -r _; }

echo "PneuComplete — dựng danh sách vật tư khí nén (chạy bằng Docker)"
echo "======================================================================"

# ---------- 1. Có Docker chưa? ----------
if ! command -v docker >/dev/null 2>&1; then
    box "✗ Máy chưa có Docker Desktop" <<'EOF'
Phần mềm này chạy trong Docker nên máy cần cài Docker Desktop một lần.

Cách cài:
  1. Vào  https://www.docker.com/products/docker-desktop
  2. Tải bản cho macOS (chú ý chọn đúng Apple Silicon hay Intel)
  3. Cài, mở Docker Desktop, chờ hình con cá voi ở thanh trên đứng yên
  4. Quay lại nháy đúp tệp này lần nữa

Không biết máy mình loại nào: bấm  → About This Mac.
Thấy chữ "Apple M1/M2/M3..." là Apple Silicon.
EOF
    hold; exit 1
fi

# ---------- 2. Docker đã CHẠY chưa? (cài rồi mà chưa mở là lỗi hay gặp nhất) ----------
if ! docker info >/dev/null 2>&1; then
    echo "Docker chưa chạy — đang thử mở Docker Desktop..."
    open -a Docker 2>/dev/null
    printf "  chờ Docker khởi động"
    for _ in $(seq 1 60); do            # tối đa ~120 giây
        if docker info >/dev/null 2>&1; then echo " → xong"; break; fi
        printf "."; sleep 2
    done
    if ! docker info >/dev/null 2>&1; then
        echo
        box "✗ Docker Desktop chưa khởi động xong" <<'EOF'
Đã cài Docker nhưng nó chưa chạy được.

Cách sửa:
  1. Mở Docker Desktop từ Launchpad
  2. Chờ tới khi hình con cá voi trên thanh menu KHÔNG còn nhấp nháy
  3. Quay lại nháy đúp tệp này lần nữa

Nếu Docker Desktop báo lỗi, chụp ảnh gửi người phụ trách.
EOF
        hold; exit 1
    fi
fi

# ---------- 3. Bật phần mềm ----------
# 'docker compose' (mới) và 'docker-compose' (cũ) — nhận cả hai.
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    box "✗ Thiếu Docker Compose" <<'EOF'
Docker có nhưng thiếu phần Compose. Hãy cập nhật Docker Desktop lên bản mới
nhất (bản mới có sẵn Compose), rồi chạy lại tệp này.
EOF
    hold; exit 1
fi

echo "Đang chuẩn bị phần mềm (lần đầu có thể mất 5–15 phút, xin chờ)..."
if ! $DC up -d --build; then
    box "✗ Không dựng được phần mềm" <<'EOF'
Docker báo lỗi khi dựng. Nguyên nhân thường gặp:

  · Máy không vào được internet (lần đầu cần tải bản Python và PyYAML)
  · Hết dung lượng ổ đĩa — cần khoảng 1 GB trống
  · Công ty chặn Docker Hub — nhờ bộ phận IT

Hãy chụp ảnh TOÀN BỘ cửa sổ này và gửi cho người phụ trách.
EOF
    hold; exit 1
fi

# ---------- 4. Chờ UI trả lời rồi mới mở trình duyệt ----------
# Mở trình duyệt quá sớm thì người dùng thấy "không kết nối được" và tưởng lỗi.
printf "Đang chờ phần mềm sẵn sàng"
READY=0
for _ in $(seq 1 45); do
    if curl -fs "$URL/api/series" >/dev/null 2>&1; then READY=1; echo " → xong"; break; fi
    printf "."; sleep 1
done

if [ "$READY" != "1" ]; then
    echo
    echo "Phần mềm chạy nhưng chưa trả lời. Log 30 dòng cuối:"
    echo "----------------------------------------------------------------------"
    $DC logs --tail 30
    echo "----------------------------------------------------------------------"
    box "! Chưa mở được trang" <<EOF
Thử mở tay địa chỉ này trong trình duyệt:  $URL

Nếu vẫn không được, chụp ảnh phần log ở trên gửi người phụ trách.
EOF
    hold; exit 1
fi

open "$URL"

box "✓ Phần mềm đang chạy" <<EOF
Địa chỉ: $URL   (trình duyệt vừa được mở)

Phần mềm chạy NGẦM — đóng cửa sổ này KHÔNG làm nó tắt.
Muốn tắt hẳn: nháy đúp tệp  Tat-PneuComplete.command

Phương án BOM bạn dựng được lưu ở thư mục  data/  cạnh tệp này.
Sao lưu thư mục đó là sao lưu toàn bộ công việc của bạn.
EOF
echo "Nhấn Enter để đóng cửa sổ này (phần mềm vẫn chạy)."
read -r _
