# Lộ trình tới phần mềm hoàn chỉnh

Viết lại sau khi đã chạy thật pha crawl / ngữ pháp / engine — nên các ước lượng dưới
đây dựa trên kinh nghiệm thực tế của dự án, không phải phỏng đoán ban đầu.

Trạng thái hiện tại (2026-08-14): kiến trúc đã chứng minh chạy được đầu-cuối, nhưng
**độ phủ dữ liệu 0,31%** (4/1.297 series có ngữ pháp) và **chưa có gì được người xác minh**.

Ký hiệu: 🔴 chặn đường · 🟡 cần dữ liệu từ bạn · ⚪ thuần kỹ thuật

---

## GIAI ĐOẠN A — Đóng vòng chất lượng TRƯỚC KHI mở rộng

Lý do A đứng trước B: ngữ pháp AS/TU/D-M9 hiện do tôi đọc PDF, chưa ai duyệt. Nếu
tôi đọc sai mà cứ thêm 10 series nữa thì chỉ nhân rộng cái sai. Đo trước, mở rộng sau.

### A1. Golden test từ BOM máy cũ 🟡
- Nhập 1–2 file Excel BOM máy cũ vào `machine` + `bom_line`
- Khớp `raw_code` → `part` (mã nào không khớp = lỗ hổng dữ liệu, ghi lại)
- Chạy engine với input = danh sách xy-lanh của máy đó, so output với BOM thật
- **Kết quả cần có**: con số đúng / thiếu / thừa theo từng tầng BOM
- Cần từ bạn: **file Excel BOM**. Không có thì mọi con số chất lượng đều là tự phong.
- ~1 ngày sau khi có file

### A2. Màn hình duyệt review_item ⚪
- 1.714 item đang pending, 0 duyệt. Cần UI tối thiểu: xem `proposed` + `diff` + nguồn
  (link tới đúng trang PDF), bấm approve / reject / edit
- Auto-approve có điều kiện (§2 DESIGN.md): mã parse lại được + spec trong dải hợp lý
  → confidence cao → cho qua, lấy mẫu 5% kiểm tay
- ~3 ngày (bản CLI/TUI tối giản: 1 ngày)

### A3. Bạn duyệt dữ liệu của 4 series đã có 🟡
- Đặc biệt: ngữ pháp AS (mã `AS2201F-01-06S` bạn sẽ đặt hàng thật) và D-M9
  (attrs `wiring`/`indicator` tôi suy từ quy ước đặt tên, không đọc trực tiếp)
- ~1 giờ, nhưng là cái quyết định mọi thứ phía sau đáng tin hay không

### A4. Baseline accuracy ⚪
- Ghi lại số đo A1 làm mốc. Mọi thay đổi sau này phải không làm tụt mốc này
- Biến A1 thành test tự động: `tests/golden/machine_*.yaml`
- ~0,5 ngày

**Cửa ra của giai đoạn A**: biết engine đúng bao nhiêu %, và biết dữ liệu nào đã được
người xác nhận. Chưa qua cửa này thì đừng làm B.

---

## GIAI ĐOẠN B — Mở rộng dữ liệu tới mức dùng được

### B1. Ngữ pháp VAN ⚪ — quan trọng nhất, khó nhất
- 198 series van, hiện 0 có ngữ pháp. Không có van thì không có BOM máy tự động
- Đã tìm được trang đúng (SY PDF trang 48, sơ đồ 11 ô) nhưng **2 vị trí chưa giải mã**:
  chữ số thứ 3 (kiểu lắp base-mounted/body-ported) và chữ số cuối trong `-5U1`
- Cách gỡ: đọc thêm trang manifold ordering + đối chiếu với 47 mã thật đã quét
- Nếu SY quá nặng, cân nhắc VQ hoặc SYJ đơn giản hơn cho máy nhỏ
- **1–2 ngày**

### B2. Ngữ pháp FRL (AC-A) ⚪
- PDF 89 trang đã tải. Cần cả bảng lưu lượng để engine chọn cỡ theo Σ flow
- **~0,5 ngày**

### B3. Ngữ pháp fitting KQ2 🔴 CHẶN
- **Không có PDF.** Trang series KQ2 không chứa link `/catalog/en/` nào
- Phải giải xong B6 trước, hoặc nhập tay từ catalog giấy/PDF bạn có
- Không có fitting thì BOM thiếu tầng nối ống — dùng được nhưng không hoàn chỉnh

### B4. Xy-lanh khác 🟡
- CJ2 (có PDF, spine không khớp — cần đọc tay), CQ2 (không PDF), MXH/MXQ, CQS…
- Chỉ encode series **bạn thực sự dùng** — cần danh sách từ bạn
- ~2 giờ/series

### B5. Tổng quát hoá parser PDF ⚪ (tuỳ chọn)
- Hiện 1/8 PDF đọc được tự động. Sửa "chọn trang HTO đúng" (rẻ) + nhánh mã liền chuỗi
- Đáng làm nếu muốn phủ 394 series có PDF; không đáng nếu chỉ cần 10 series
- **3–5 ngày**, rủi ro cao

### B6. Giải quyết coverage PDF 31% 🔴
- Chỉ 394/1.297 series có link PDF. `ca01.smcworld.com` trả 403 cho directory listing
- Ba hướng: (a) tìm endpoint JSON của trang viewer catalog; (b) dùng trang
  "Operation Manuals / Documents" làm nguồn khác; (c) **xin file dữ liệu chính thức
  từ nhà phân phối SMC Việt Nam** — hướng này giải luôn cả rủi ro pháp lý
- ~1 ngày điều tra (a)(b); (c) phụ thuộc SMC

### B7. Bảng giá 🟡
- `price` đang rỗng. Cần file Excel price list từ nhà phân phối
- Có giá thì BOM mới xuất được để mua hàng, và ranking mới xét được chi phí
- ~0,5 ngày sau khi có file

---

## GIAI ĐOẠN C — Hoàn thiện engine

### C1. Consolidate thật ⚪
- Hiện gộp số lượng là xong. Cần thêm:
  - đếm van → chọn **số station manifold** (phụ thuộc B1)
  - Σ flow → **cỡ ống trục chính** + kiểm tổn thất áp
  - gộp fitting theo từng mối nối (phụ thuộc B3)
- ~2 ngày

### C2. Kiểm chéo Cv van ⚪
- Luật đã thiết kế cần `cv_min` nhưng chưa có dữ liệu Cv. Phải trích bảng
  Specifications trong PDF van (`parsers/pdf_spec_table.py` — chưa viết)
- ~1,5 ngày

### C3. Duyệt đồ thị giao diện nhiều bước ⚪
- Hiện `mates()` chỉ xét 1 mối nối. Cần lan truyền: cửa xy-lanh → speed controller →
  ống → fitting → manifold → FRL → nguồn, và báo mọi giao diện còn hở
- Đây mới là "constraint propagation" đầy đủ như §0 DESIGN.md
- ~2 ngày

### C4. Cooccurrence từ BOM cũ ⚪
- Khai thác `bom_line` → cặp series hay đi cùng → xếp hạng candidate
- Phụ thuộc A1. Không làm trước khi engine đúng — nếu không chỉ là nhiễu
- ~1 ngày

### C5. Đề xuất luật từ dữ liệu ⚪
- Màn hình "SMC ghi applicable accessory cho series này" → gợi ý luật để bạn xác nhận
- Nguồn: trang "Applicable ..." đã crawl nhưng chưa parse
- ~1,5 ngày

---

## GIAI ĐOẠN D — Web app

### D1. Backend API ⚪
- FastAPI: `POST /bom` (nhập actuator → BOM), `GET /series`, `GET /part/{pn}`,
  `GET/POST /review` (duyệt), `GET /project/{id}`
- ~3 ngày

### D2. Frontend ⚪
- Nhập danh sách actuator (paste từ Excel được), xem BOM 4 tầng có giải thích,
  chỉnh số lượng, giải quyết gap, xuất file
- Màn hình duyệt review (gộp với A2 nếu A2 làm bản web luôn)
- ~5 ngày

### D3. Xuất Excel theo mẫu công ty 🟡
- Cần **mẫu Excel của phòng mua hàng**
- ~1 ngày

### D4. Chuyển SQLite → Postgres ⚪
- `db/schema.sql` đã viết sẵn cho Postgres. Cần: Alembic migrations, đổi
  `json_extract` → `->>`/`@>`, index GIN, FTS5 → pg_trgm
- Chỉ cần khi có nhiều người dùng đồng thời
- ~2 ngày

---

## GIAI ĐOẠN E — Vận hành

### E1. Re-crawl định kỳ ⚪
- Catalog SMC đổi bản vài lần/năm. Cơ chế sha256 đã có → chỉ parse cái thay đổi
- Cron + báo cáo "series nào đổi spec" → vào review queue
- ~1 ngày

### E2. Alembic + backup + deploy ⚪
- ~1,5 ngày

### E3. Quyết định pháp lý 🟡
- `robots.txt` của SMC: `ai-train=no, use=reference`. Dùng nội bộ tra cứu là được phép
- Nhưng **nếu định bán hoặc phát hành ra ngoài** thì cần đọc Terms of Use và xin phép
- Việc cần bạn quyết: phần mềm này chỉ dùng nội bộ, hay có ý định thương mại?

---

## Bản tối giản dùng được thật (MVP)

Nếu chỉ muốn nhanh nhất có thể dùng cho công việc thật, cắt còn:

```
A1  golden test              (cần file BOM cũ của bạn)
A3  bạn duyệt 4 series       1 giờ
B1  ngữ pháp van             1–2 ngày
B2  ngữ pháp FRL             0,5 ngày
B4  2–3 xy-lanh bạn hay dùng 0,5 ngày
B7  bảng giá                 (cần file price list)
C1  consolidate manifold+ống 2 ngày
D3  xuất Excel đúng mẫu      1 ngày
```
≈ **6–8 ngày làm việc** + 3 file từ bạn (BOM cũ, price list, mẫu Excel).
Chạy bằng CLI, chưa cần web. Fitting vẫn là gap (B3 bị chặn).

## Bản hoàn chỉnh

Tổng A→E ≈ **7–9 tuần** làm việc liên tục, với điều kiện:
- B3 và B6 được gỡ (hoặc chấp nhận phủ 30% catalog)
- Bạn cấp được: BOM cũ, price list, mẫu Excel xuất, danh sách series thường dùng
- B5 (tổng quát hoá parser) là phần rủi ro nhất — có thể đội thêm 1 tuần

## Ba việc chỉ bạn làm được

Không có ba thứ này thì phần mềm không thể hoàn chỉnh, dù tôi viết bao nhiêu code:

1. **File BOM máy cũ** → thước đo chất lượng duy nhất đáng tin
2. **Duyệt dữ liệu** → ngữ pháp tôi đọc từ PDF cần kỹ sư xác nhận trước khi đặt hàng thật
3. **Danh sách series thực dùng** → để khỏi encode 1.297 series mà chỉ cần 15
