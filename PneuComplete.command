#!/bin/bash
# Nháy đúp tệp này để mở PneuComplete.
# Nếu macOS báo "không thể mở vì chưa xác định nhà phát triển":
#   nháy phải vào tệp → Open → Open.

cd "$(dirname "$0")" || exit 1

# tìm python3: ưu tiên bản trong PATH, sau đó các vị trí cài phổ biến trên macOS
PY=""
for c in python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
         /usr/bin/python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo
  echo "┌────────────────────────────────────────────────────────────────┐"
  echo "│ ✗ Máy chưa cài Python                                          │"
  echo "├────────────────────────────────────────────────────────────────┤"
  echo "│ PneuComplete cần Python 3.10 trở lên để chạy.                  │"
  echo "│                                                                │"
  echo "│ Cách cài: mở trang python.org → Downloads → tải bản cho macOS  │"
  echo "│ → cài đặt → mở lại tệp PneuComplete.command này.               │"
  echo "└────────────────────────────────────────────────────────────────┘"
  echo
  echo "Nhấn Enter để đóng."
  read -r _
  exit 1
fi

exec "$PY" start.py
