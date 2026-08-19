# PneuComplete

Phần mềm hoàn thiện BOM khí nén: nhập vài xy-lanh, phần mềm suy ra phần còn lại
(van, phụ kiện, ống, FRL, cảm biến) **kèm lý do cho từng dòng**.

Không dùng học máy. Lý do: chỉ có vài BOM lịch sử — học máy sẽ đoán. Phần mềm
suy luận trên **đồ thị giao diện lắp ghép** cộng **quy tắc kỹ thuật** đọc từ
catalog; thống kê chỉ dùng để xếp hạng giữa các phương án đã hợp lệ.
Chỗ nào không đủ dữ liệu thì **báo gap**, không đoán bừa.

- Người dùng cuối → `HUONG-DAN-SU-DUNG.md`
- Chi tiết kiến trúc → `docs/DESIGN.md`
- Đóng gói / Docker → `docker/README.md`
- Lộ trình → `docs/ROADMAP.md`

## Chạy sau khi clone

Repo **không chứa** `pneu.db` (360 MB, có BOM khách hàng). Lấy bản hạt giống
sạch đã commit:

```sh
cp db/seed/pneu-seed.db pneu.db
```

Rồi chọn một cách chạy:

```sh
# A. Docker (khuyến nghị — không cần cài gì ngoài Docker Desktop)
docker compose up -d --build          # → http://localhost:8765

# B. Trực tiếp (cần Python 3.10+ và PyYAML)
pip3 install pyyaml
python3 start.py
```

## Test

```sh
python3 tests/test_parser.py     #  6 — parse mã hàng
python3 tests/test_bom.py        # 26 — luật + dựng BOM
python3 tests/test_web.py        #  7 — API web
python3 tests/test_docker.py     # 61 — đóng gói Docker (không cần daemon)
```

## Dòng lệnh

```sh
python3 -m engine.cli "CDM2L32-500Z x4 valve=double" --tube-total-m 60
python3 -m ingest.golden show                 # so BOM engine sinh vs BOM đã mua
python3 tools/package.py                      # → dist/PneuComplete.zip
python3 tools/package.py --clean-db           # → dist/pneu.db (bản sạch)
```

## Dựng lại dữ liệu từ đầu

Chỉ cần khi cập nhật catalog SMC. `series` và `category` đến từ crawl nên
**không sinh lại được chỉ từ các tệp `.yaml`** — phải có `cache/` hoặc crawl lại.

```sh
python3 -m crawler.run init
python3 -m crawler.run crawl          # ≤1 req/s, tôn trọng robots.txt
python3 -m crawler.run reparse        # parse lại từ cache — 0 request
python3 -m crawler.run grammar        # nạp db/seed/grammar/*.yaml
```

## Điều cần biết trước khi sửa

| Đường dẫn | Vì sao quan trọng |
|---|---|
| `db/seed/grammar/*.yaml` | 15 ngữ pháp mã hàng **nhập tay từ catalog**, mỗi tệp ghi rõ PDF + số trang + chỗ nào là suy đoán. Tri thức quý nhất của project. |
| `db/seed/rules.yaml` | 12 quy tắc kỹ thuật; mỗi quy tắc có `rationale` (hiện lên UI) và `source`. |
| `db/seed/interfaces.yaml` | Template cửa/ren cho từng họ — nền tảng của suy luận. |
| `series.grammar_source` | `'manual'` được **bảo vệ** khỏi bộ parse máy. Từng bị parser ghi đè làm vỡ ngữ pháp TU. |

**Không commit:** `pneu.db`, `BOM/`, `DOCUMENT/`, `cache/`, `answer1.xlsx` — xem
`.gitignore`, mỗi dòng có ghi lý do.

## Nguồn dữ liệu

Crawl từ [smcworld.com](https://www.smcworld.com/webcatalog/en-jp/). robots.txt
của họ ghi `Content-Signal: ai-train=no, use=reference` — thiết kế dựa-trên-quy-tắc
này tuân thủ (không huấn luyện mô hình). Crawler dùng UA riêng
`PneuCompleteBot/0.1`, không giả làm trình duyệt, ≤1 request/giây.
**`Allow` không phải giấy phép bản quyền** — dùng nội bộ, muốn phát hành phải xin
phép SMC.
