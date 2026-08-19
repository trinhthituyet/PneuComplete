# PneuComplete — Thiết kế hệ thống

Phần mềm gợi ý/hoàn thiện BOM khí nén: người dùng nhập vài actuator, hệ thống suy ra
toàn bộ phần còn lại (van, manifold, FRL, ống, phụ kiện) kèm lý do và cảnh báo thiếu.

---

## 0. Nguyên tắc thiết kế cốt lõi

**Đây KHÔNG phải bài toán machine learning.** Với vài BOM cũ, ML sẽ đoán bừa. Bản chất
đây là bài toán **thoả ràng buộc (constraint satisfaction)** trên đồ thị giao diện kết nối,
cộng thêm luật kỹ thuật. ML/thống kê chỉ dùng để **xếp hạng** khi có nhiều lựa chọn hợp lệ.

Ba nhận xét quyết định toàn bộ schema:

1. **Mã hàng SMC là mã ghép (compositional), không phải danh sách phẳng.**
   `CDM2 L 32 -500 Z` = 5 ô: series + mounting + bore + stroke + hậu tố.
   Nếu lưu SKU phẳng thì phải sinh hàng triệu dòng và vẫn thiếu. → Lưu **ngữ pháp mã**
   (`code_slot` + `code_option`), rồi *materialize* thành `part` khi cần.

2. **Cái làm nên khả năng "dự đoán" là GIAO DIỆN KẾT NỐI, không phải tên sản phẩm.**
   Xy-lanh ø32 không "cần AS2201F". Nó **có 2 cửa khí ren Rc 1/8 (female)**. Bất cứ thứ gì
   có đầu `thread/Rc/1-8/male` đều lắp được. → Bảng `part_interface` là trái tim hệ thống.
   Thêm hãng khác, thêm series mới đều không phải sửa code.

3. **BOM có 2 tầng suy luận khác nhau:**
   - *Per-item* (nhân theo từng xy-lanh): speed controller, cảm biến, bracket, fitting.
   - *System-level* (cộng dồn rồi mới chọn): số station của manifold, cỡ FRL theo tổng
     lưu lượng, cỡ ống trục chính, tổng chiều dài ống.
   Engine phải chạy 2 pha: fan-out rồi consolidate.

---

## 1. Kiến trúc

```
┌─────────────────────────────────────────────────────────┐
│ UI (React)   nhập actuator → BOM có giải thích + gap    │
└────────────────────────┬────────────────────────────────┘
                         │ REST /api
┌────────────────────────┴────────────────────────────────┐
│ ENGINE (Python)                                          │
│  parse mã → fire luật → giải ràng buộc → gộp → xếp hạng │
└────────────────────────┬────────────────────────────────┘
┌────────────────────────┴────────────────────────────────┐
│ POSTGRES                                                 │
│  catalog (series/part/interface) · rule · bom_history    │
└────────────────────────┬────────────────────────────────┘
┌────────────────────────┴────────────────────────────────┐
│ INGEST                                                   │
│  CRAWLER smcworld ─→ CACHE thô (đĩa + sha256, bất biến) │
│         ─→ PARSER ─→ REVIEW QUEUE (người xác nhận) ─→ DB│
│  (+ PDF/Excel bạn có: đối chiếu chéo & bảng giá)        │
└─────────────────────────────────────────────────────────┘
```

Nguyên tắc bất di bất dịch của tầng ingest: **crawl và parse là hai bước rời nhau**. Crawler chỉ
tải và lưu nguyên trạng; parser đọc từ cache. Nhờ vậy khi parser sai (chắc chắn sẽ sai nhiều lần
ở giai đoạn đầu), bạn sửa parser rồi chạy lại trên cache — không tải lại trang nào, không bị SMC
chặn IP vì crawl lặp.

Điểm quan trọng: **có bước REVIEW của người trong ingest**. Sai một ký tự mã hàng = đặt
sai hàng, mất tiền và thời gian. Không bao giờ để dữ liệu trích tự động đi thẳng vào
trạng thái `is_verified = true`.

---

## 2. Database — vì sao thiết kế như vậy

Xem `db/schema.sql` để có DDL đầy đủ. Giải thích các bảng then chốt:

### `series` + `code_slot` + `code_option` — ngữ pháp mã hàng
Cho phép 2 việc: **parse** (`CDM2L32-500Z` → `{bore:32, mounting:'axial_foot', stroke:500}`)
và **generate** (biết cần bore 32 + foot → sinh đúng mã). Mỗi `code_option` mang `attrs`
JSONB chứa spec mà lựa chọn đó kéo theo — ví dụ option bore `32` mang
`{"bore_mm":32, "port_size":"Rc1/8", "area_push_mm2":804}`. Parse xong chỉ cần merge attrs
của các option là có đầy đủ spec, không cần bảng spec riêng cho từng bore.

### `part` — mã đã hoàn chỉnh
Chỉ materialize những mã thực sự dùng (nhập tay, xuất hiện trong BOM cũ, hoặc engine sinh ra).
`attrs` JSONB + index GIN → truy vấn theo spec rất nhanh:
`where attrs @> '{"port_size":"Rc1/8"}'`. Không dùng cột cứng vì mỗi loại sản phẩm có tập
spec hoàn toàn khác nhau (xy-lanh có bore/stroke, van có Cv/voltage, ống có OD/ID/màu).

### `part_interface` — trái tim
Mỗi sản phẩm khai báo các "chân cắm" của nó:

| part | role | kind | gender | standard | size | tube_od | qty |
|---|---|---|---|---|---|---|---|
| CDM2L32-500Z | air_port | thread | female | Rc | 1/8 | – | 2 |
| CDM2L32-500Z | switch_rail | rail | – | SMC-D | – | – | 2 |
| AS2201F-01-06S | inlet | thread | male | R | 1/8 | – | 1 |
| AS2201F-01-06S | outlet | onetouch | female | – | – | 6 | 1 |
| TU0604BU | end | tube | – | – | – | 6 | 2 |

Quy tắc ghép (mate): `kind` tương thích · `standard`+`size` khớp · `gender` ngược nhau.
Suy luận trở thành duyệt đồ thị: xy-lanh có cửa hở → tìm part có đầu ghép được → cửa mới hở
(one-touch ø6) → tìm ống ø6 → … dừng khi tới nguồn khí.

### `rule` — luật kỹ thuật, lưu trong DB không hard-code
`when_expr` / `then_spec` là JSONB. Sửa luật = sửa dữ liệu, không deploy lại. Mỗi luật có
`rationale` + `source` (trang catalog hoặc tên người quyết định) → BOM xuất ra luôn giải
thích được. Xem `db/seed/rules.example.yaml`.

### `machine` + `bom_line` + `cooccurrence` — học từ BOM cũ
Nạp vài Excel cũ vào đây dùng cho 3 việc:
- **Bộ kiểm chứng**: chạy engine với input = danh sách xy-lanh của máy cũ, so output với BOM
  thật. Đây là thước đo chất lượng duy nhất đáng tin.
- **Khai thác luật ngầm**: cặp series hay đi cùng nhau (support/confidence/lift) → gợi ý cho
  bạn *xác nhận thành luật*, chứ không tự động thành luật.
- **Xếp hạng**: khi 5 speed controller đều hợp lệ, ưu tiên mã bạn đã dùng.

### `source_doc` — truy xuất nguồn
Mọi part/spec đều trỏ về URL + sha256 + thời điểm tải (hoặc file PDF + số trang). Khi số liệu
đáng ngờ, mở đúng nguồn để đối chiếu trong 5 giây.

### `crawl_target` + `crawl_fetch` — hàng đợi và cache thô
`crawl_target` là hàng đợi URL có trạng thái (`pending/fetching/done/failed`), tự bồi thêm khi
phát hiện link mới, có `attempts` + `last_error` để retry chọn lọc. `crawl_fetch` ghi mỗi lần tải:
HTTP status, sha256, đường dẫn file trên đĩa. **Body không nhét vào Postgres** — để trên đĩa,
DB chỉ giữ metadata. Hai lợi ích cụ thể:
- **Re-crawl gia tăng**: sha256 không đổi → bỏ qua, không parse lại. Catalog SMC đổi bản vài lần
  một năm, không cần tải lại toàn bộ.
- **Chạy lại parser miễn phí**: sửa parser → chạy lại trên cache, 0 request.

### `extract_run` + `review_item` — chốt chất lượng
Crawl cho ra dữ liệu **nhiều hơn và bẩn hơn** PDF thủ công, nên hàng đợi review là bắt buộc, không
phải tuỳ chọn. Parser không ghi thẳng vào `part`; nó đẻ ra `review_item` chứa `proposed` (JSONB),
`diff` so với dữ liệu đang có, và `confidence`. Người duyệt → mới vào `part` với
`is_verified = true`. `extract_run` lưu `parser_version` để biết dòng nào do parser bản nào sinh ra
— khi phát hiện parser v3 sai, truy ngược đúng tập dữ liệu cần duyệt lại.

Chiến lược duyệt thực dụng: **auto-approve có điều kiện**. Nếu mã sinh ra parse lại được bằng
code grammar, spec nằm trong dải hợp lý, và khớp với PDF/BOM cũ → `confidence` cao, cho qua tự
động, chỉ lấy mẫu 5% kiểm tay. Phần còn lại duyệt tay. Không có cơ chế này thì 5.000 part sẽ chôn
bạn ở màn hình review.

---

## 3. Thuật toán suy luận

```
INPUT: [{CDM2L32-500Z ×5}] + config (áp suất, chu kỳ, điện áp, ren, ống, tự động hoá)

1. PARSE       mã → series + attrs (qua code grammar). Mã lạ → hỏi người dùng.
2. EXPAND      fire luật theo scope per_actuator → sinh REQUIREMENT
               (category + ràng buộc spec + công thức qty), chưa phải mã hàng.
3. RESOLVE     mỗi requirement → truy vấn candidate: khớp interface + thoả ràng buộc spec.
4. RANK        (a) interface khớp tuyệt đối  (b) lift từ BOM cũ  (c) đã có trong kho/giá
5. CONSOLIDATE tổng hợp toàn hệ:
               • đếm van → chọn manifold đủ station
               • Σ lưu lượng (L/min ANR) → chọn cỡ FRL (+ hệ số an toàn 1.5)
               • cỡ ống trục chính theo Σ flow & tổn thất áp cho phép
               • gộp trùng, cộng chiều dài ống, cộng fitting
6. VALIDATE    kiểm chéo: Cv van ≥ Cv yêu cầu? tốc độ piston trong dải cho phép?
               điện áp cuộn coil đồng nhất? ren đồng chuẩn?  → cảnh báo
7. EXPLAIN     mỗi dòng BOM mang rule_id + rationale + độ tin cậy
8. GAP         requirement không giải được → "cần bạn quyết định", KHÔNG đoán bừa
```

Bước 8 là bước giữ uy tín phần mềm. Thà báo thiếu 3 dòng còn hơn điền 3 mã sai.

**Ví dụ vết chạy** (input: 5× CDM2L32-500Z, 0.5 MPa, 1.5 s/hành trình, DC24V, ống ø6):

| Bước | Suy ra | Luật / căn cứ |
|---|---|---|
| parse | bore 32, stroke 500, có nam châm (D), cushion (Z), cửa Rc1/8 | code grammar CM2 |
| expand | 2 speed ctrl/xy-lanh, ren R1/8, ống ø6 | R-SPD-01 |
| expand | 2 cảm biến từ/xy-lanh (vì có "D") | R-SW-01 |
| expand | 1 van 5/2 double/xy-lanh (auto, 2 chiều dừng được) | R-VLV-01 |
| resolve | AS2201F-01-06S · D-M9BW · SY3200-5U1 | interface match + lift BOM cũ |
| consolidate | 5 van → manifold SS5Y3-10F1-05D-C6 (5 station) | R-MFD-01 |
| consolidate | Σ 160 L/min × 1.5 → FRL 3/8: AC30-03DG-B | R-FRL-01 |
| validate | Cv cần 0.32 ≤ Cv SY3200 = 0.38 ✓ | tính toán |
| validate | ⚠ ø6 @ 333 mm/s → tổn thất ~8%, khuyến nghị ø8 | tính toán |
| gap | chưa biết kiểu đầu cần (I-M1004B?) → hỏi | – |

---

## 4. Nạp dữ liệu — crawl smcworld là nguồn chính

### 4.1 Crawler tách 2 tầng

```
tầng 1  FETCH   crawl_target (hàng đợi) → httpx, 1 req/s, robots-aware
                → lưu nguyên trạng vào cache/<sha[:2]>/<sha256>.<ext>
                → ghi crawl_fetch (status, sha256, path, elapsed)
                ── KHÔNG parse gì ở tầng này ──

tầng 2  PARSE   đọc cache → parser theo loại trang
                → review_item (proposed + diff + confidence)
                → người duyệt / auto-approve có điều kiện → part, code_option, ...
```

Tầng 1 chạy chậm và một lần; tầng 2 chạy lại bao nhiêu lần cũng được. Trạng thái nằm trong DB nên
crawler sập giữa đường thì chạy lại là tiếp tục đúng chỗ cũ, không cần logic resume riêng.

### 4.2 Pha RECON — ĐÃ LÀM ✅

Kết quả đầy đủ ở `docs/RECON.md` (khảo sát 2026-08-13, 8 request). Tóm tắt những gì chốt được:

| Câu hỏi | Kết quả thật |
|---|---|
| robots.txt cho `/webcatalog/`? | ✅ `Allow: /`, không `Crawl-delay`, không `Sitemap` |
| Render kiểu gì? | ✅ **Server-rendered** HTML + jQuery, không phải SPA |
| Có endpoint JSON? | ❌ Không. Search chạy Fess, dựng bằng JS, trả rỗng |
| URL có quy luật? | ✅ Rất rõ, xem §4.3 |
| Dữ liệu dạng gì? | Bảng HTML cho variation & Made-to-Order · **PDF cho How-to-Order và spec** |

Hai điều làm thay đổi thiết kế:

- **Bỏ hẳn Playwright.** Không cần trình duyệt ở bất cứ đâu, kể cả recon về sau.
- **Bỏ hẳn BFS.** Có `/webcatalog/en-jp/indexSearch/<A..Z>` trả về bảng HTML sạch
  (`Category | Product name | Series | Type | Detail`) — 26 request là có danh mục series toàn
  catalog. Ngoài ra mega-menu trong **một** trang category chứa luôn **1.896 URL series**.
  Discovery gần như miễn phí.

### 4.3 Đường lấy dữ liệu đã chốt: HTML + PDF

```
seed    /webcatalog/en-jp/indexSearch/<A..Z>        → bảng series toàn catalog (26 req)
series  /webcatalog/en-jp/seriesList/?id=<SERIES>-E → URL chuẩn, ổn định hơn URL semantic
        (dạng semantic tương đương:
         /webcatalog/en-jp/<category>/<subcategory>/<SERIES>-E)
pdf     /catalog/en/<group>/<SERIES>-E/<doc>/data/<doc>.pdf
        → 302 → ca01.smcworld.com   ⚠ HOST KHÁC, phải cho vào allowlist của cả crawler
```

Allowlist / denylist cho crawler (từ robots.txt thật):
```python
ALLOW = r'^/webcatalog/en-jp/(seriesList/|indexSearch/|[a-z0-9-]+/)'
DENY  = r'^/(products/[^/]+/(global|ps)\.do|support/req/)'   # robots.txt Disallow
MAX_DEPTH = 3
```

Khối lượng thật: 10 series ≈ 22 request (vài phút). Toàn catalog ≈ 1.922 trang HTML ≈ 32 phút ở
1 req/s. **Tầng HTML rẻ hơn dự kiến rất nhiều**; chi phí thật nằm ở xử lý PDF.

### 4.4 Trang nào đáng crawl trước

Ưu tiên **không** theo thứ tự trang xuất hiện trên web, mà theo giá trị cho engine:

1. **PDF catalog của series** — chứa **How to Order** (sinh ra `code_slot`/`code_option`, tức toàn
   bộ khả năng parse mã hàng) + bảng Specifications + bảng port size. Một sơ đồ How-to-Order giá
   trị hơn 50 trang spec. Xác nhận được: HTML **không** có How-to-Order, chỉ PDF có.
2. **Bảng HTML trên trang series** — lấy được ngay mà không cần PDF:
   - bảng variation (`Type / Series / Action / Bore size`) → `series` + option bore
   - bảng Simple Specials `-XA…` và Made to Order `-XB/-XC…` → `code_option` ô hậu tố
3. **`indexSearch/A..Z`** — seed bảng `series` + phân loại category.
4. **Trang phụ kiện / "Applicable ..."** — SMC ghi thẳng phụ kiện tương thích cho từng series.
   Đây là luật kỹ thuật được cho không, đừng tự nghĩ ra.
5. Bỏ qua: bản vẽ kích thước, file CAD, hình ảnh sản phẩm — không phục vụ suy luận.

### 4.5 PDF catalog — đã kiểm, trích được text ✅

Rủi ro số 1 của dự án đã được loại bỏ. Kiểm trên PDF CM2 thật (8,2 MB, 102 trang, PDF 1.6):

| Kiểm tra | Kết quả |
|---|---|
| `pdftotext -layout` | ✅ 888 KB text từ 102 trang — **không phải ảnh scan** |
| "How to Order" trong PDF | ✅ 12 lần |
| Cặp `mã → nhãn` của option | ✅ `B Basic`, `L Axial foot`, `F Rod flange`, `Nil Pneumatic`… |
| `pdftotext -bbox-layout` | ✅ toạ độ từng từ (915 word/trang) |

**Cách trích code grammar — thuật toán rút ra từ dữ liệu thật:**

Sơ đồ How-to-Order là hình 2D, nên chế độ `-layout` **trộn các cột rời rạc vào cùng một dòng**
(ví dụ dòng `L Axial foot E Integrated clevis * Air-hydro type: Rc only` là ba cột khác nhau bị dán
lại). Vì vậy phải dùng `-bbox-layout` rồi xử lý theo toạ độ:

```
1. SPINE   Tìm dòng chứa mã mẫu — trên trang CM2 nó nằm nguyên vẹn:
             y=186   CM2    B    40   150   A   Z
             y=210   CDM2   B    40   150   A   Z   M9BW
             x=      73/81  126  141  182   206 250 307
           → có ngay số ô, thứ tự ô, và toạ độ x của từng ô.

2. BAND    Cụm word theo x thành các dải cột (x<165, 165–310, >310), đọc từng dải
           độc lập. Đây là bước gỡ đúng cái mà -layout làm hỏng.

3. BLOCK   Trong mỗi dải, gom theo y thành cặp (mã, nhãn):
             B → Basic (Double-side bossed)     L → Axial foot
             A → Air cushion                    Nil → Pneumatic

4. MAP     ★ Mẹo then chốt: SPINE chứa một giá trị mẫu cụ thể cho MỖI ô.
           Khớp từng token của spine với block chứa đúng mã đó:
             spine "B"     → block có "B Basic ..."      ⇒ block này là ô mounting
             spine "A"     → block có "A Air cushion"    ⇒ ô cushion
             spine "40"    → block có 20/25/32/40        ⇒ ô bore
             spine "M9BW"  → bảng auto switch            ⇒ ô auto_switch
           Ghép ô gần như tự động, không phải đoán.

5. REVIEW  Token nhập nhằng (`Nil` xuất hiện ở nhiều block; `A` cũng có ở y=510) →
           ưu tiên khớp token đặc trưng trước (M9BW, 40, Z), phần còn lại suy ra bằng
           loại trừ + tính đơn điệu của thứ tự x. Còn nhập nhằng thì đẩy vào review_item.
```

Kết luận: grammar **tự động hoá được**, không phải nhập tay. Phương án nhập tay 10 series giữ lại
làm dự phòng cho series nào có sơ đồ vẽ khác thường.

Fixture để phát triển parser offline: `tests/fixtures/smcworld/cm2_p6.bbox.xml` (trang How-to-Order,
có toạ độ) và `cm2_p6.layout.txt`. Nguồn ghi ở `SOURCES.txt` cùng thư mục.

⚠️ Lưu ý hạ tầng: PDF **redirect sang host `ca01.smcworld.com`**. Crawler phải cho phép cross-host
redirect tới host này, và allowlist phải có cả hai host.

### 4.6 Quy tắc lịch sự và pháp lý


Bắt buộc trong crawler, không phải khuyến nghị:

- Đọc và tuân `robots.txt` (`urllib.robotparser`), kiểm tra trước mỗi URL, cache kết quả.
- **≤ 1 request/giây, đồng thời = 1** cho cùng host. Token bucket, không dùng `sleep` rải rác.
- Backoff luỹ thừa + jitter khi gặp 429/5xx; tôn trọng header `Retry-After`.
- User-Agent nhận diện được, kèm email liên hệ. Đừng giả làm Chrome.
- Chạy ngoài giờ cao điểm nếu crawl khối lượng lớn.

Về pháp lý, giờ có dữ liệu thật để nói chính xác. `robots.txt` của SMC mang **Content-Signal**:

```
Content-Signal: search=yes, ai-train=no, use=reference
```

Nghĩa là SMC **cấm** dùng nội dung để huấn luyện/fine-tune model AI, nhưng **cho phép** dùng làm
tài liệu tham chiếu. PneuComplete rơi đúng vào phần được phép: ta xây database tra cứu và suy luận
bằng luật, không huấn luyện model nào. Đây là thêm một lý do nữa để **không** đi hướng ML — ngoài
lý do kỹ thuật ở §0, còn là lý do tuân thủ.

Hai điều vẫn phải nhớ: (a) SMC chặn riêng loạt AI crawler có tên (ClaudeBot, GPTBot, CCBot,
Google-Extended…), cho thấy họ để ý chuyện này — crawler của bạn phải khai UA riêng, đúng danh
tính, đừng giả dạng trình duyệt; (b) `Allow` trong robots.txt **không phải giấy phép bản quyền**.
Dùng nội bộ thì ổn và phổ biến trong ngành; phát hành hoặc bán ra ngoài thì cần đọc Terms of Use
và nên xin phép. Đường an toàn cho đường dài: chạy nội bộ bằng crawl, song song xin file dữ liệu
chính thức từ nhà phân phối SMC Việt Nam — đổi nguồn chỉ sửa tầng ingest, không chạm engine.

### 4.7 PDF/Excel bạn có — giờ là nguồn đối chiếu

Không bỏ, mà chuyển vai: dùng để **kiểm tra chéo** kết quả crawl (số liệu lệch → parser sai) và
để nạp **bảng giá** (crawl không có giá). Đây chính là cơ chế nâng `confidence` cho auto-approve
ở §2.

```
Excel price list → pandas → khớp part_number → bảng price
PDF             → pdfplumber/camelot → so với part đã crawl → chênh thì gắn cờ review
```

---

## 5. Lộ trình

| Pha | Việc | Kết quả kiểm chứng được | Ước lượng |
|---|---|---|---|
| **0** | Chốt phạm vi: 5–10 series đang dùng, chuẩn ren, ống, điện áp mặc định | 1 trang danh mục series | 1 ngày |
| **1** | ~~RECON~~ **ĐÃ XONG** → `docs/RECON.md` | ✅ chốt được đường HTML+PDF, allowlist, khối lượng | ~~0.5–1 ngày~~ |
| **2** | Postgres + schema + **crawler tầng 1**: hàng đợi, rate limit, robots, cache sha256, resume. Seed từ `indexSearch/A..Z` | crawl đủ trang của **1 series**; chạy lại lần 2 không phát request nào | 2–3 ngày |
| **3** | Parser **How-to-Order** → `code_slot`/`code_option` cho CM2 + AS2000 | parse `CDM2L32-500Z` ra đúng spec, và sinh lại đúng mã (round-trip) | 1 tuần |
| **4** | Parser bảng spec + cỡ cửa · review queue · auto-approve có điều kiện · mở crawl ra 5–10 series | ≥ 300 part `is_verified`, tỉ lệ auto-approve ≥ 60% | 1.5–2 tuần |
| **5** | `part_interface` + engine pha per-actuator (bước 1–4) | 5 xy-lanh → ra đúng speed ctrl, sensor, fitting | 1 tuần |
| **6** | Pha consolidate + validate (bước 5–6): manifold, FRL, ống, tính toán | so với 1 BOM máy cũ, khớp ≥ 80% dòng | 1–1.5 tuần |
| **7** | Nạp BOM cũ → cooccurrence → xếp hạng + màn hình "gợi ý luật" | BOM cũ thành test suite tự động | 4–5 ngày |
| **8** | Web UI: nhập actuator, xem BOM có giải thích, xuất Excel/PDF | dùng được cho máy thật | 1–1.5 tuần |

Tổng ~8–11 tuần. Đổi sang crawl làm nguồn chính đắt hơn dùng PDF sẵn có khoảng **2–3 tuần** —
đổi lại được độ phủ rộng hơn nhiều và cập nhật lại được khi SMC ra bản catalog mới.

Ba quy tắc thứ tự, vi phạm là mất thời gian:

- **Crawl hẹp trước, rộng sau.** Pha 2 chỉ crawl 1 series. Chứng minh parser đúng trên 1 series
  (pha 3) rồi mới mở rộng (pha 4). Crawl 5.000 trang bằng parser sai = 5.000 dòng rác phải duyệt tay.
- **Không làm pha 7 trước pha 5.** Chưa có engine đúng thì thống kê từ BOM cũ chỉ là nhiễu.
- **Không làm UI trước pha 6.** UI đẹp trên logic sai là cái bẫy: nó làm bạn tin phần mềm đã xong.

**Mốc kiểm chứng bắt buộc sau pha 6:** lấy 1 máy cũ, che BOM, cho engine chạy, đếm số dòng
đúng / thiếu / thừa. Dưới 70% thì sửa luật trước khi làm tiếp UI.

---

## 6. Stack & cấu trúc repo

```
PneuComplete/
├─ db/
│  ├─ schema.sql              DDL
│  ├─ migrations/             alembic
│  └─ seed/rules.example.yaml luật mẫu
├─ cache/                     ← response thô, content-addressed, KHÔNG commit
│  └─ <sha[:2]>/<sha256>.<ext>
├─ crawler/                   ← tầng 1: chỉ tải và lưu
│  ├─ frontier.py             hàng đợi crawl_target, ưu tiên, retry
│  ├─ fetcher.py              httpx + token bucket 1 req/s + backoff
│  ├─ robots.py               kiểm tra robots.txt, cache
│  ├─ store.py                ghi cache + crawl_fetch
│  └─ discover.py             sinh URL mới, allowlist regex + depth limit
├─ parsers/                   ← tầng 2: cache → review_item
│  ├─ html_index.py           indexSearch/A..Z → bảng series (seed)
│  ├─ html_series.py          trang series → variation + Made-to-Order → code_option
│  ├─ html_accessory.py       "Applicable ..." → gợi ý luật
│  ├─ pdf_how_to_order.py     sơ đồ mã hàng trong PDF → code_slot/code_option  ★ then chốt
│  ├─ pdf_spec_table.py       bảng spec trong PDF → part.attrs
│  ├─ pdf_port_table.py       cỡ cửa/ống trong PDF → part_interface
│  └─ price_import.py         Excel bảng giá
├─ engine/
│  ├─ parser.py               mã hàng ⇄ spec
│  ├─ interfaces.py           mate matching
│  ├─ rules.py                fire luật
│  ├─ consolidate.py          manifold/FRL/ống
│  ├─ calc.py                 lực, lưu lượng, Cv, tốc độ
│  └─ explain.py              vết suy luận
├─ api/                       FastAPI (+ endpoint review queue)
├─ web/                       React + Vite (+ màn hình duyệt dữ liệu)
├─ docs/
│  ├─ DESIGN.md
│  └─ RECON.md                ← kết quả pha 1 (đã xong)
└─ tests/
   ├─ test_parser.py
   ├─ fixtures/smcworld/      trang thật đã tải lúc recon, test parser offline
   └─ golden/machine_*.yaml   BOM cũ làm golden test
```

Postgres 16 · Python 3.12 · SQLAlchemy + Alembic · httpx · selectolax (nhanh hơn BeautifulSoup
nhiều) · `pdftotext -layout` (có sẵn trên máy) · FastAPI · React + Vite + TanStack Query.
**Không cần Playwright** — recon đã xác nhận trang server-rendered. Chưa cần pgvector/LLM ở lõi.

`cache/` phải vào `.gitignore` — nó sẽ phình lên nhiều GB. (Đã tạo `.gitignore`.)

---

## 7. Câu hỏi còn mở (điền ở pha 0)

1. Danh sách chính xác 5–10 series đang dùng thường xuyên? (quyết định phạm vi crawl)
2. Chuẩn ren mặc định (Rc / NPT / G) và ống mặc định (ø4/6/8/10, PU hay nylon)?
3. Điện áp cuộn coil chuẩn (DC24V / AC220V) và kiểu đầu nối (grommet / L-plug / M8)?
4. Có dùng hãng khác trộn vào (Festo, Airtac, CKD) không? — schema đã sẵn cột `maker`.
5. BOM cần xuất theo mẫu nào (mẫu Excel của công ty / phòng mua hàng)?
6. Phần mềm chỉ dùng nội bộ, hay sau này phát hành/bán ra ngoài? — quyết định mức độ phải cẩn
   trọng với dữ liệu crawl (§4.5).
7. Máy chạy crawler có IP tĩnh / mạng công ty không? Nếu bị chặn thì crawl từ đâu.

---

## 10. Học thói quen người dùng (2026-08-19)

Bổ sung này **xét lại** quyết định gốc ở §1 ("suy luận theo ràng buộc, không dùng
học máy"). Lý do gốc vẫn đúng — 2 BOM thì thống kê là đoán — nhưng số liệu đo
trên chính dữ liệu đó cho thấy có một loại tri thức học được chắc chắn.

### Đo được gì

| | máy 23-432 | máy 24-236 | |
|---|---|---|---|
| push-lock (-A) | 32/32 | 37/37 | **100%, 69 mẫu** |
| `KQ2L` / xy-lanh | 1.59 | 4.62 | lệch 2.9× |
| `KQ2U` / xy-lanh | 1.76 | 3.81 | lệch 2.2× |
| `JA30` / xy-lanh | 0.29 | 0.06 | lệch 4.8× |

Kết luận: **học LỰA CHỌN được, học SỐ LƯỢNG không.** Và điều quan trọng về mặt
thiết kế: bằng chứng cho lựa chọn nằm TRONG một BOM (32 cái push-lock trong cùng
một máy là 32 lần khẳng định), nên không cần chờ nhiều máy.

### Bốn tầng bằng chứng, thứ tự ưu tiên tường minh

```
1  RÀNG BUỘC (part_interface + thread_compat)   → CHẶN, học không được vượt
2  KHUYẾN NGHỊ CATALOG                          → tiên nghiệm
3  THỐNG KÊ TỪ BOM CÔNG TY (engine/learn.py)    → chỉ cho LỰA CHỌN
4  CẤU HÌNH BẠN KHAI                            → LUÔN THẮNG
```

Tri thức học được chỉ **xếp hạng giữa các phương án đã hợp lệ**. Học "thích
push-lock" thì tốt; "M5 lắp vào R1/8" phải bị chặn ở tầng 1. Và tầng 3 không bao
giờ ghi đè tầng 4 — nếu ngược lại thì người dùng mất quyền điều khiển một cách âm
thầm (`test_hoc_khong_ghi_de_cau_hinh_ban_khai` canh điều này).

### Phân loại khoá (engine/learn.py)

`HABIT_KEYS` = thuộc tính người mua, chuyển được sang máy mới: họ speed
controller, núm, màu ống, chiều dài cuộn, thế hệ FRL.

`MACHINE_KEYS` = phụ thuộc lưu lượng/layout, **phải khai lại từng máy**: cỡ van,
ø ống, tổng mét, cỡ FRL, kiểu manifold, kiểu gá van.

Cảnh báo N=2: `tube_od_mm=6` và `valve_series_size=SY5000` giống nhau ở cả hai
máy, nhưng chúng do lưu lượng quyết định. Hai máy có 17 và 16 xy-lanh — gần bằng
nhau — nên **không tách được "thói quen" khỏi "trùng hợp vì máy cùng cỡ"**. Xếp
vào `MACHINE_KEYS` là phía an toàn.

### Ngưỡng và cách xử lý mâu thuẫn

Dùng làm mặc định khi: thuộc `HABIT_KEYS` · mâu thuẫn ≤ ½ số ủng hộ · thấy ở ≥2
máy **hoặc** lặp ≥10 lần trong 1 máy.

**Mâu thuẫn thì HỎI, không lấy trung bình.** Trung bình của 1 và 14 là 7 — con số
không tồn tại trong thực tế.

### Chưa khai và chưa học được thì sao

Phân theo HẬU QUẢ của việc đoán sai, không theo "có phải sở thích hay không":

| | Xử lý | Vì sao |
|---|---|---|
| lệch **số lượng** (`tube_roll_length_m`) | **gap**, không đoán | mặc định 20 m cho ra `TU0604BU-20 ×15` trong khi thật là `TU0604B-200 ×1` — sai 15× |
| lệch **biến thể** (màu, hậu tố, thế hệ) | ra dòng + cảnh báo `PREF_GUESSED` | bỏ luôn dòng thì mất giá trị "không bỏ sót"; số lượng vẫn đúng, và số lượng mới là chỗ tốn tiền |

### Đo trung thực: bỏ ra một máy

`ingest/golden.py` học từ các máy **khác** máy đang chấm (`learn_exclude`). Học từ
chính máy đang chấm rồi báo điểm là đưa trước đáp án.

Hệ quả: điểm từ **36% → 17%**. 36% là con số bị rò đáp án. 17% là thật.

Điều đáng giá hơn con số: với bỏ-ra-một-máy, **mã speed controller đúng ở cả hai
máy** (`AS2201F-01-06SA`, `AS1201F-M5-06A`) — thói quen chuyển được sang máy chưa
từng thấy. Chỉ số lượng lệch, mà số lượng đã biết là không suy được.

Với 2 máy, bỏ-ra-một-máy nghĩa là học từ đúng 1 máy, nên điều kiện "≥2 máy" không
bao giờ đạt — chỉ tín hiệu lặp nhiều (speed controller, 69 mẫu) sống sót. **Đây là
giới hạn của dữ liệu, không phải của thuật toán.** Thêm máy thứ ba là mở ra ngay.
