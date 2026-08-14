# RECON — khảo sát smcworld.com

Trạng thái: **ĐÃ LÀM XONG** · 2026-08-13 · thực hiện bằng curl, 9 request, ~1 req/s

Kết luận ngắn: **thuận lợi hơn dự kiến, và rủi ro số 1 đã được loại bỏ.** Webcatalog là
server-rendered HTML với URL có quy luật rõ, có sẵn **index A–Z** liệt kê toàn bộ series dạng bảng
HTML sạch. Không cần Playwright, không cần BFS. PDF catalog **có text trích được** (không phải ảnh
scan) và sơ đồ How-to-Order dựng lại được bằng toạ độ — grammar tự động hoá được.

---

## 1. robots.txt ✅

```
User-agent: *
Content-Signal: search=yes,ai-train=no,use=reference
Allow: /

# ... các AI crawler bị chặn riêng:
User-agent: Amazonbot | Applebot-Extended | Bytespider | CCBot | ClaudeBot
         | CloudflareBrowserRenderingCrawler | Google-Extended | GPTBot
         | meta-externalagent
Disallow: /

User-agent: *
Disallow: /products/*/global.do
Disallow: /products/*/ps.do
Disallow: /support/req/*
```

- ✅ `/webcatalog/` **không** bị Disallow. `User-agent: *` được `Allow: /`.
- ✅ **Không có `Crawl-delay`** → tự đặt 1 req/s.
- ❌ **Không có `Sitemap:`** → nhưng không cần, xem §3.
- ⚠️ Ba đường phải loại trong allowlist của crawler: `/products/*/global.do`,
  `/products/*/ps.do`, `/support/req/*`.

### Đọc kỹ phần Content-Signal — nó ảnh hưởng tới dự án

`ai-train=no, use=reference`: SMC **cấm** dùng nội dung để huấn luyện/fine-tune model AI, nhưng
**cho phép** dùng làm tài liệu tham chiếu. Thiết kế PneuComplete rơi đúng vào phần được phép: ta
xây database tra cứu và suy luận bằng luật, **không** huấn luyện model nào. Giữ nguyên hướng này
thì không vi phạm content signal.

Hai điều vẫn phải nhớ: (a) SMC chặn riêng loạt AI crawler có tên (ClaudeBot, GPTBot, CCBot…), cho
thấy họ để ý chuyện này — crawler của bạn phải khai UA riêng, đúng danh tính, đừng giả dạng;
(b) `Allow` trong robots.txt không phải giấy phép bản quyền. Dùng nội bộ thì ổn; phát hành hoặc
bán ra ngoài thì cần đọc Terms of Use và nên xin phép.

## 2. Kiểu render ✅ Server-rendered

| Kiểm tra | Kết quả |
|---|---|
| `/webcatalog/en-jp/` | HTTP 200, `text/html`, 74 KB |
| Framework SPA (`#app`, `#root`, `#__next`) | **không có** |
| JS | jQuery 3.1.1 + script thường, không phải SPA |
| Trang series CM2 | 418 KB, **4 bảng HTML** có dữ liệu thật |

→ **Không cần Playwright.** httpx + selectolax là đủ. Bỏ hẳn đường C ở `DESIGN.md` §4.3.

## 3. Enumerate series — không cần BFS ✅

Hai cơ chế, dùng cả hai để đối chiếu:

**a) Index A–Z** — `/webcatalog/en-jp/indexSearch/<LETTER>`
Trả về **một bảng HTML sạch**: `Category | Product name | Series | Type | Detail`.
Riêng chữ C có **361 dòng**. 26 request là có danh mục series đầy đủ toàn catalog.
Đây là nguồn seed hoàn hảo cho bảng `series` — máy đọc được, không cần PDF.

**b) Mega-menu** — bất kỳ trang category nào cũng chứa **toàn bộ cây link**.
Một lần fetch `/webcatalog/en-jp/air-cylinders/` cho ra **1.896 URL trang series** duy nhất.

## 4. Quy luật URL ✅

```
category      /webcatalog/en-jp/<category-slug>/                    (44 category cấp 1)
subcategory   /webcatalog/en-jp/<category>/<subcategory>/
series        /webcatalog/en-jp/<category>/<subcategory>/<SERIES>-E
series (canon)/webcatalog/en-jp/seriesList/?id=<SERIES>-E           ← dùng cái này, ổn định hơn
index A–Z     /webcatalog/en-jp/indexSearch/<A..Z>
PDF catalog   /catalog/en/<group>/<SERIES>-E/<doc>/data/<doc>.pdf
              → 302 → https://ca01.smcworld.com/catalog/...          ⚠ HOST KHÁC
```

Ví dụ thật đã xác nhận:
```
/webcatalog/en-jp/air-cylinders/air-cylinders-round-type/CM2-CDM2-Z-E
/webcatalog/en-jp/seriesList/?id=CJP2-CDJP2-CJP-E
/webcatalog/en-jp/indexSearch/C
/catalog/en/actuator/CM2-CDM2-Z-E/7-3-2-p0231-0332-CM2_en/data/7-3-2-p0231-0332-CM2_en.pdf
```

Allowlist regex đề xuất:
```python
ALLOW = r'^/webcatalog/en-jp/(seriesList/|indexSearch/|[a-z0-9-]+/)'
DENY  = r'^/(products/[^/]+/(global|ps)\.do|support/req/)'
MAX_DEPTH = 3
```

## 5. Dữ liệu nằm ở dạng nào — điểm quan trọng nhất

Trang series CM2 (`CM2-CDM2-Z-E`) có gì:

| Loại dữ liệu | Dạng | Dùng cho |
|---|---|---|
| Bảng variation: `Type / Series / Action / Bore size` | ✅ bảng HTML | `series`, một phần `code_option` (bore 20/25/32/40) |
| Simple Specials `-XA0…XA30` | ✅ bảng HTML | `code_option` ô hậu tố |
| Made to Order `-XB6/-XB7/-XB9/-XC…` (25 dòng) | ✅ bảng HTML | `code_option` ô hậu tố + mô tả |
| **How to Order / Model Designation** | ❌ **không có trong HTML** (đếm được 0 lần) | ← nằm trong PDF |
| Specifications chi tiết | ⚠️ tên mục có, số liệu trong PDF | `part.attrs` |
| Port size | ⚠️ trong PDF | `part_interface` |

**Đây đúng là rủi ro đã dự đoán ở bản nháp trước.** How-to-Order chỉ có trong PDF catalog.
**§8 đã kiểm và giải quyết xong:** PDF là catalog chính thức đầy đủ (file CM2 phủ trang 231–332,
102 trang), text trích được bằng `pdftotext`, và sơ đồ dựng lại được bằng toạ độ.

Ngoài ra, mấy bảng Made-to-Order và variation ở dạng HTML sạch là **quà không ngờ**: một phần
`code_option` lấy được mà không cần chạm vào PDF.

## 6. Endpoint tìm kiếm sản phẩm ❌ không dùng được

`/webcatalog/en-jp/search3S/?kw=CDM2L32-500Z&lang=en-US` → HTTP 200 nhưng **1.061 byte, rỗng**.
Form tên `FessForm01` → chạy trên Fess (search engine OSS), kết quả dựng bằng JS. Không dùng làm
đường lấy dữ liệu. Không đào thêm — vì §3 đã đủ để enumerate.

## 7. Ước lượng khối lượng crawl

| Phạm vi | HTML | PDF | Thời gian @1 req/s |
|---|---|---|---|
| **10 series (pha 0–4)** | ~12 | ~10 | vài phút |
| Toàn catalog | 26 + 1.896 ≈ 1.922 | ~1.900 (nhiều file dùng chung) | HTML ~32 phút |

Tầng HTML rẻ đến mức bất ngờ. Chi phí thật nằm ở dung lượng và xử lý PDF, không nằm ở số request.

## 8. PDF catalog ✅ ĐÃ KIỂM — có text, không phải ảnh

Host `ca01.smcworld.com` đã được mở, tải và kiểm xong.

```
GET /catalog/en/actuator/CM2-CDM2-Z-E/7-3-2-p0231-0332-CM2_en/data/7-3-2-p0231-0332-CM2_en.pdf
→ 302 → ca01.smcworld.com/...      HTTP 200, application/pdf, 8.645.992 B, 1,9 s
PDF 1.6, 102 trang
pdftotext -layout  → 888.696 B text, 7.997 dòng
```

Đếm từ khoá trong text: `Bore size` 308 · `Stroke` 538 · `Mounting` 366 · `Auto switch` 364 ·
`Cushion` 221 · `Specifications` 68 · `How to Order` 12. → Toàn bộ nội dung kỹ thuật đọc được.

**Spine của sơ đồ How-to-Order dựng lại nguyên vẹn** (trang PDF số 6, `-bbox-layout`, 915 word):

```
y=186   CM2    B    40   150   A   Z
y=210   CDM2   B    40   150   A   Z   M9BW
x=      73/81  126  141  182   206 250 307
```

Và các cặp `mã → nhãn` lấy được đúng:
```
B  Basic (Double-side bossed)      T   Head trunnion        Nil  Pneumatic
L  Axial foot                      E   Integrated clevis    H    Air-hydro
F  Rod flange                      V   Integrated clevis (90°)   A  Air cushion
G  Head flange                     BZ  Boss-cut/Basic
C  Single clevis                   FZ  Boss-cut/Rod flange
D  Double clevis                   UZ  Boss-cut/Rod trunnion
U  Rod trunnion
```

Đối chiếu ngược với câu hỏi ban đầu: `CDM2 L 32 -500 Z` → `CDM2` = có nam châm (auto switch),
`L` = **Axial foot**, `32` = bore 32. Khớp đúng.

⚠️ Hai cạm bẫy phát hiện được, phải xử lý trong parser:

1. **`-layout` trộn các cột rời rạc vào cùng một dòng.** Ví dụ dòng thật:
   `L  Axial foot   E Integrated clevis   * Air-hydro type: Rc only` — ba cột khác nhau bị dán lại.
   → Bắt buộc dùng `-bbox-layout` và phân dải theo x trước khi đọc.
2. **PDF ở host khác** (`ca01.smcworld.com`): crawler phải cho phép cross-host redirect, và
   allowlist/robots check phải áp cho cả hai host.

Thuật toán trích grammar 5 bước (SPINE → BAND → BLOCK → MAP → REVIEW) ghi ở `DESIGN.md` §4.5.
Mấu chốt: spine chứa **một giá trị mẫu cho mỗi ô**, khớp giá trị đó với block chứa cùng mã là ghép
được ô gần như tự động.

---

## Kết luận chốt

- **Đường lấy dữ liệu: HTML server-rendered + PDF.** Không có JSON endpoint dùng được; không cần
  Playwright.
- **Seed = `indexSearch/A..Z`** (26 request) → danh mục series đầy đủ. Không BFS, không sitemap.
- **Grammar tự động hoá được** từ PDF bằng `-bbox-layout` + phân tích toạ độ. Phương án nhập tay
  giữ làm dự phòng cho series có sơ đồ vẽ khác thường.
- **Rủi ro còn lại đã hạ xuống mức trung bình:** không còn rủi ro chặn đường, chỉ còn công sức làm
  parser cho các biến thể layout khác nhau giữa các series.
- Điều chỉnh lộ trình: pha 2 nhẹ hơn (không Playwright, discovery gần miễn phí) → tiết kiệm ~2–3
  ngày. Pha 3 giữ nguyên ước lượng nhưng độ tin cậy cao hơn nhiều.

## Phụ lục — fixture đã lưu

`tests/fixtures/smcworld/` — dùng để phát triển và test parser **offline, không cần mạng**.
URL nguồn của từng file ghi trong `SOURCES.txt` cùng thư mục.

| File | Nội dung |
|---|---|
| `robots.txt` | 65 dòng |
| `wc_index.html` | trang chủ webcatalog, 73 KB |
| `pg_air-cylinders_.html` | category air-cylinders, 397 KB, chứa 1.896 link series |
| `pg_indexSearch_C.html` | index chữ C, 481 KB, bảng 361 dòng |
| `cm2.html` | trang series CM2, 408 KB, 4 bảng |
| `srch.html` | kết quả search rỗng, 1 KB — bằng chứng §6 |
| `cm2_p6.bbox.xml` | **trang How-to-Order kèm toạ độ từng word** — fixture quan trọng nhất |
| `cm2_p6.layout.txt` | cùng trang, chế độ `-layout`, để so sánh thấy vấn đề trộn cột |
| `cm2_p7.layout.txt` | trang Specifications, fixture cho parser bảng spec |

PDF gốc 8,2 MB không commit (xem `.gitignore`); URL tái tải ghi trong `SOURCES.txt`.
