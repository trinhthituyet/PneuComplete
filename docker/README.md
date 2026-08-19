# Docker — ghi chú cho người bảo trì

Người dùng cuối không cần đọc tệp này; họ đọc `HUONG-DAN-SU-DUNG.md`.

## Vì sao dùng Docker

Toàn bộ project theo hướng chỉ-stdlib (urllib để crawl, zipfile để đọc .xlsx,
pdftotext để đọc PDF) — trừ **một** phụ thuộc: **PyYAML**. Nó nằm ngay trên
đường chạy chính của UI:

- `engine/bom.py` → `seed_rules()` đọc `db/seed/rules.yaml`
- `engine/materialize.py` → `load_templates()` đọc `db/seed/interfaces.yaml`

Có hai cách xử lý, đã thử cả hai:

| Cách | Vấn đề |
|---|---|
| Sinh bản `.json` song song, đọc bằng stdlib | Hai bản dễ lệch nhau. Và YAML cho phép **khoá số nguyên** (`map: {20: "1/8"}`), JSON thì không — lần chuyển đổi đầu tiên làm **mất toàn bộ cỡ cửa**, 26 test đỏ. |
| **Docker (đang dùng)** | Cần cài Docker Desktop một lần. Bù lại `.yaml` là bản **duy nhất**. |

Nhánh đọc `.json` vẫn còn trong `engine/conf.py` làm phương án cho máy không cài
được Docker: `python3 tools/package.py --json-only`.

## Lệnh thường dùng

```sh
docker compose up -d --build      # bật (lần đầu tự build)
docker compose down               # tắt
docker compose logs -f            # xem log
docker compose restart            # khởi động lại sau khi sửa mã

# chạy lệnh trong container
docker compose run --rm app python3 tests/test_bom.py
docker compose run --rm app python3 -m engine.cli "CDM2L32-500Z x4 valve=double"
docker compose run --rm app python3 -m ingest.golden show
```

## Build ảnh để GỬI RA NGOÀI

`pneu.db` ở thư mục gốc trên máy phát triển **có BOM máy của khách hàng** (bảng
`machine`, `bom_line`) và nặng hàng trăm MB. Không build thẳng từ nó:

```sh
python3 tools/package.py --clean-db                          # → dist/pneu.db, 0.8 MB
PNEU_DB_FILE=dist/pneu.db docker compose up -d --build       # hoặc:
docker build --build-arg DB_FILE=dist/pneu.db -t pneucomplete .
```

Trong gói `dist/PneuComplete.zip` thì `pneu.db` đã là bản sạch, nên người dùng
cứ `docker compose up` là đúng.

## Ba quyết định dễ làm sai

**1. Trong container phải bind `0.0.0.0`.**
`127.0.0.1` bên trong container chỉ nghe loopback **của container** → host không
vào được, mà log vẫn báo "đang chạy". Đặt qua `PNEU_HOST` (Dockerfile + compose).
Mặc định khi chạy ngoài Docker vẫn là `127.0.0.1` — bind `0.0.0.0` trên máy người
dùng là mở phần mềm (không có đăng nhập) cho cả mạng LAN.

**2. Dữ liệu phải nằm ngoài ảnh.**
DB mẫu ở `/seed/pneu.db` trong ảnh; lúc khởi động `docker/entrypoint.sh` chép
sang `/data/pneu.db` **chỉ khi chưa có**. Nếu đặt DB mẫu thẳng ở `/data` thì
volume che mất nó; nếu chép mỗi lần khởi động thì xoá sạch phương án của người
dùng. `tests/test_docker.py` kiểm đúng hai điều này.

**3. Cổng map là `127.0.0.1:8765:8765`, không phải `8765:8765`.**
Dạng sau mở cho cả mạng LAN. Muốn cho cả xưởng dùng chung thì đổi — và hiểu rằng
phần mềm không có đăng nhập, ai trong mạng cũng xem/sửa được phương án.

## Test

`tests/test_docker.py` (61 phép kiểm) chạy **không cần Docker daemon**: nó kiểm
logic của `entrypoint.sh`, biến môi trường, tính nhất quán của
Dockerfile/compose/.dockerignore, và hàm đặt quyền tệp trong .zip.

**Nó KHÔNG thay được việc build và chạy ảnh thật.** Lần đầu build phải làm bằng
tay và xem UI có mở được không.
