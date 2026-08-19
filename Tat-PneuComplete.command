#!/bin/bash
# Tắt PneuComplete (macOS).
#
# Vì sao cần tệp riêng: bản Docker chạy NGẦM, đóng cửa sổ đen không tắt nó.
# Phương án BOM đã dựng nằm ở thư mục data/ nên tắt KHÔNG mất dữ liệu.

cd "$(dirname "$0")" || exit 1
export PATH="$PATH:/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$HOME/.docker/bin"

if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi

echo "Đang tắt PneuComplete..."
$DC down
echo
echo "✓ Đã tắt. Dữ liệu trong thư mục data/ vẫn còn nguyên."
echo "  Muốn dùng lại: nháy đúp PneuComplete-Docker.command"
echo
echo "Nhấn Enter để đóng cửa sổ."
read -r _
