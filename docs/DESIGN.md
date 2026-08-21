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

## 10. Báo lỗi 3 phần + engine tự quyết (2026-08-21)

Hai spec: `Prompt sửa cách báo lỗi của PneuComplete.md` và
`spec-cai-tien-so-do-khi-nen_1.md`.

### 10.1 Báo lỗi 3 phần

`engine/problem.py` chuẩn hoá mọi vấn đề thành: **sai ở đâu · cần sửa gì · sửa
thế nào** (+ liệt kê lựa chọn). Mọi thứ dài — catalog, Cv, số trang, logic — vào
`detail`, UI gập lại trong `<details>`.

Trước: một gap FRL hiện 667 ký tự rationale, người dùng đọc 8 câu mới biết cần
điền ô nào. Sau: 1 câu + tên field + danh sách nút bấm để chọn thẳng.

`code` giữ là **định danh máy đọc** ổn định, KHÔNG suy từ `field` — suy như vậy
sinh ra mã vô nghĩa kiểu `EDGE.KIND` và đổi theo nhãn.

### 10.2 Engine tự chọn cỡ van từ lưu lượng

`db/seed/charts/sy-flow.yaml` + `engine/chart.py`. Dẫn nạp âm C trích từ catalog
SY trang 43; catalog tự ghi `S = 5.0 × C`. ISO 6358 định nghĩa ở chảy tắc
`q[dm³/s ANR] = C × p1[bar abs]`, nên `Q_max = 60·C·(MPa·10 + 1,013)`.

```
SY3000 C=1,3 → 469 L/min      SY5000 C=3,1 → 1118      SY7000 C=4,4 → 1587
```

Kiểm chứng: 4× CDM2L32-500Z cần 1065 L/min → **SY5000**, đúng cỡ BOM máy 23-432
dùng. Ngoài dải đã số hoá thì **báo gap, không ngoại suy**.

Bảng đang `needs_review: true` vì bảng trong PDF **gộp hàng** — đã lấy C **nhỏ
nhất** của mỗi cỡ, sai theo hướng đó chỉ chọn van to hơn cần.

### 10.3 Cái giá của "engine tự quyết loại van" — đo được

Spec yêu cầu engine tự đề xuất `valve_function` thay vì để trống. Đã làm. Nhưng
phải nói rõ cái giá, vì nó ngược với bằng chứng đã đo trước đó:

| | trước | sau |
|---|---|---|
| golden test | 36% (11 dòng trong mẫu số) | **18%** (22 dòng) |
| van trong mẫu số | không — engine từ chối đoán | có — engine đoán nên phải đo |

Máy 23-432: engine đề xuất `SY5220-5MZE-C6 ×17`, thực tế `×2`, và **bỏ sót**
`SY5120` (single ×5) + `SY5420` (3-pos ×4).

Điểm tụt KHÔNG phải vì engine tệ hơn, mà vì **trước đây van được loại khỏi phép
đo**. Engine đã ngừng từ chối đoán thì che kết quả là tự lừa — nên
`ingest/golden.py` chỉ còn xếp "không đo được" khi engine THẬT SỰ không đề xuất gì.

Giảm thiểu: dòng van do engine suy bị **hạ tin cậy xuống 50%** ngay trên dòng, để
người ký BOM thấy chỗ cần kiểm. Bạn khai tay thì 90%.

### 10.4 Sơ đồ: 4 sửa đổi

| Mục | Việc | Ghi chú |
|---|---|---|
| 4 | dây neo đúng tâm cổng | **lỗi thật**: `.pts` là `position:relative` đặt sau header nên gốc toạ độ lệch ~70px so với `portPos()`. Nay `absolute; inset:0` |
| 1 | Manhattan routing thay spline | tối đa 3 đoạn vuông góc, bo góc r=6 bằng cung Q, tránh đè thân node, re-route khi kéo |
| 2 | cổng chỉ hiện khi mã hợp lệ | chưa có mã → "chưa xác định cổng", không hiện cổng giả định |
| 3 | bố trí theo datasheet | van 5/2: 2/A·4/B trên · 3/R–**1/P**–5/S dưới (P giữa) · coil hàng riêng |
| 5 | điền mã ngược vào sơ đồ | gán theo `for_items` (dòng BOM sinh vì actuator nào), không theo thứ tự |

`tests/test_ui.js` nay kiểm cả **CSS** `.node .pts`, vì bài học: bản trước test
`portPos()` xanh mà UI vẫn sai — test chỉ kiểm một phía của hợp đồng.
