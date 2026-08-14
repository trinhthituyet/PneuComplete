# Kết quả crawl toàn bộ HTML — 2026-08-13

Chạy: `init` → `crawl` (38,4 phút) → `reparse` (0 request) → `backfill`.

## Đã có gì

| | Số lượng |
|---|---|
| Trang tải được | **2.185** (26 index A–Z · 88 category · 338 subcategory · 1.733 series) |
| Cache trên đĩa | **889 MB**, 2.188 file, content-addressed theo sha256 |
| `series` | **1.296** (1.059 từ indexSearch + 237 phát hiện thêm qua mega-menu) |
| `category` | 175 · phân layer: actuator 376, valve 198, electrical 154, air_prep 93, piping 83, accessory 38, other 351 |
| `review_item` | **1.665** chờ duyệt (926 option hậu tố · 469 bore · 270 đề xuất sub-series) |
| `crawl_fetch` / `extract_run` | 2.185 / 2.093 |
| DB | `pneu.db`, 5,1 MB |

## Chưa có gì — và vì sao

```
code_slot       0
code_option     0
part            0
part_interface  0
```

Toàn bộ dữ liệu cấp mã hàng nằm trong **1.252 PDF đang xếp hàng đợi** (`kind='pdf'`,
`state='pending'`) — theo đúng lựa chọn "HTML toàn bộ + hàng đợi PDF". HTML chỉ cho được
bộ xương catalog.

Quan trọng: **1.665 review_item đang bị chặn bởi PDF.** Mỗi item đều mang ghi chú
*"cần How-to-Order để chốt vị trí ô"* — biết bore là 20/25/32/40 nhưng chưa biết ô bore
nằm ở vị trí nào trong mã. Không parse PDF thì không duyệt được, và không có `code_slot`
thì không parse được `CDM2L32-500Z`. PDF nằm trên đường tới hạn.

## Lỗi và loại bỏ

| | Số | Ghi chú |
|---|---|---|
| 404 | 30 | Link chết trong chính mega-menu của SMC (`/leak-detector/`, `SJ3A6-E`, `VEX3-E`…). Đã ghi `last_error`, chạy lại được. |
| Bỏ chủ động | 228 | `?view=picture` — trùng byte với URL gốc |
| Series chưa gán category | 3 | URL không theo quy luật |

## Ba phát hiện làm thay đổi thiết kế

**1. `?view=list` là mỏ dữ liệu, `?view=picture` là rác.** Trang subcategory mặc định có
**0 bảng**; `?view=list` gộp bảng variation + Made-to-Order của *toàn bộ* series trong
subcategory (guide-cylinders: 28 bảng / 1 trang). `?view=picture` trùng byte với trang gốc.
Đã thêm `_DUP_VIEW` vào `discover.py` để loại `picture`, và viết `parsers/html_subcat.py`
riêng cho `list`.

**2. Bảng variation có 4 HOẶC 5 cột** (`Type | [Bearing] | Series | Action | Bore size`),
lại còn dùng rowspan nên số ô mỗi dòng không đều. Bản v1 hardcode `r[1]`=series nên thu
được `'Slide bearing'`, `'Double acting'`, `'3.5'` — sai 59% số dòng. v2 nhận cột theo
**mẫu nội dung** thay vì vị trí. Sau khi sửa: variations 470 → **1.012**.

Đây là lúc kiến trúc tách 2 tầng trả nợ: sửa parser rồi `reparse` toàn bộ 2.067 trang từ
cache, **0 request**, không phải crawl lại 38 phút.

**3. indexSearch không liệt kê hết series.** `CJ2K-Z`, `CM2K-Z`, `CJPB` xuất hiện trong
bảng variation nhưng không có trong index — SMC gộp chúng vào mã nhóm. 270 trường hợp,
giờ vào review queue dưới dạng `entity_type='series'` chờ xác nhận là series riêng hay
biến thể.

## Kiểm chứng: CM2 có đủ dữ liệu chưa

```
#571  CM2/CDM2-Z   catalog_id=CM2-CDM2-Z-E   "Air Cylinder CM2 (With auto switch)"
      bore   [20, 25, 32, 40]
      suffix XA0  Change of rod end shape
             XB6  Heat resistant cylinder (−10 to 150℃)
             XB7  Cold resistant cylinder (−40 to 70℃)
             XB9  Low speed cylinder (10 to 50 mm/s)
             XB12 External stainless steel cylinder
             XC3  Special port location
             XC4  With heavy duty scraper
```
Đủ để nhận ra `32` là bore hợp lệ, nhưng **chưa** đủ để biết `L` = Axial foot hay vị trí ô
mounting — cái đó trong PDF.

## Lệnh

```bash
python3 -m crawler.run init       # tạo DB + seed 27 URL
python3 -m crawler.run crawl      # crawl HTML, PDF chỉ xếp hàng đợi
python3 -m crawler.run reparse    # chạy lại parser trên cache, 0 request
python3 -m crawler.run backfill   # gán category từ URL cho series thiếu
python3 -m crawler.report         # báo cáo
```

Ctrl-C rồi chạy lại `crawl` là tiếp tục đúng chỗ cũ — trạng thái nằm trong DB.

---

# Pha 3 — PDF + ngữ pháp mã hàng (cùng ngày)

## Đã tải

8 PDF của bộ SLICE, **109,4 MB**: SY-E 73,2 MB/370 trang · AC-A-E 13,3 MB/89 ·
CM2 8,6 MB/102 · CJ2 8,1 MB/119 · AS-FS-E 5,0 MB/19 · AS-E-E 0,8 MB/9 ·
D-M9-5-E 0,2 MB/2 · TU-E 0,1 MB/2.

## Kết quả: CM2 chạy đúng hoàn toàn

`parsers/pdf_how_to_order.py` v3 dựng được ngữ pháp CM2 từ trang 6 của PDF:

| pos | ô | kiểu | option |
|---|---|---|---|
| 1 | mounting | enum | **13** — B/T/L/E/F/V/G/BZ/C/FZ/D/UZ/U |
| 2 | bore | enum | 4 — 20/25/32/40 |
| 3 | stroke | integer | sep `-` |
| 4 | cushion | enum | 2 — Nil=Rubber bumper, A=Air cushion |
| 5 | series_suffix | enum | 1 — Z (cố định) |
| 6 | auto_switch | free | — |

`engine/parser.py` parse được mã thật:

```
CDM2L32-500Z        → ok  mounting=L (Axial foot) bore=32 stroke=500
                          cushion=Nil (Rubber bumper) has_magnet=True
CM2B40-150AZ        → ok  mounting=B bore=40 stroke=150 cushion=A (Air cushion)
CDM2B32-100AZ-M9BW  → ok  + auto_switch=M9BW
CDM2X99-500Z        → KHÔNG ok, báo `unparsed='X99-500Z'`  (không đoán bừa)
```

4/4 test hồi quy pass: `python3 tests/test_parser.py`.

## Nhưng: chỉ 1/8 PDF chạy được

| series | trang có "How to Order" | spine tìm được | ô đặt tên được |
|---|---|---|---|
| **CM2-CDM2-Z-E** | 12 | `CDM2 B 40 150 A Z M9BW` | **6/6** |
| TU-E | 1 | `TU0425 BU 20` | 1/2 |
| CJ2-CDJ2-Z-E | 18 | không thấy | 0 |
| AS-E-E | 3 | không thấy | 0 |
| AS-FS-E | 1 | không thấy | 0 |
| AC-A-E | 13 | không thấy | 0 |
| D-M9-5-E | 1 | không thấy | 0 |
| SY-E | 104 | không thấy | 0 |

Đây là rủi ro đã cảnh báo ở `DESIGN.md` §4.5 — **mỗi họ series vẽ sơ đồ một kiểu**,
và các ngưỡng hình học (`LABEL_DX=70`, `RUN_GAP_DY=14`, `MERGE_DX=70`) được rút ra từ
đúng một trang của CM2.

Chẩn đoán từng ca (chưa kết luận nguyên nhân cho mọi ca):

- **CJ2** trang 6: không có dòng nào mà token đầu trông như mã series → sơ đồ có thể
  vẽ mã thành **một chuỗi liền** (`CDJ2B16-45Z`) thay vì các ô rời. Nếu đúng thì cần
  nhánh xử lý riêng, không dùng được logic spine hiện tại.
- **AS-E-E** trang 2: là **biểu đồ đặc tính lưu lượng**, không phải sơ đồ How-to-Order.
  Phải thử 2 trang HTO còn lại trước khi kết luận.
- **SY-E**: 104 trang HTO trong catalog manifold 370 trang — nhiều sub-series, trang đầu
  chỉ có một cột option (`C3 C4 C6 C8 C10 C12`), spine nằm ở trang khác. Cần chọn trang
  đúng thay vì lấy trang HTO đầu tiên.
- **TU-E**: spine `TU0425 BU 20` tìm được nhưng đây là ống — mã gộp cả OD/ID vào một
  token (`0425`), cần luật tách riêng.

## Việc còn lại, theo thứ tự tới hạn

1. **Chọn trang HTO đúng** thay vì trang đầu tiên. Rẻ, chắc chắn giúp SY và có thể AS.
2. **Nhánh spine cho mã liền chuỗi** (CJ2). Trung bình.
3. Quyết định: tiếp tục tổng quát hoá parser, hay **nhập tay ngữ pháp cho ~10 series**
   (~1–2 giờ/series). Parser tổng quát mở rộng được tới 398 series có PDF; nhập tay
   chắc chắn 100% nhưng không mở rộng. CM2 đã chứng minh thuật toán đúng về nguyên lý.
4. Điều tra **coverage PDF chỉ 31%**: chỉ 398/1.296 series có link PDF catalog trong HTML
   đã crawl. CQ2 và KQ2 không có — trang series của chúng không hề chứa link `/catalog/en/`,
   dù trang CM2 thì có. Directory listing trên `ca01.smcworld.com` trả 403 nên không
   enumerate được. Cần tìm nguồn khác cho 69% còn lại.

---

# Pha B — nhập tay ngữ pháp (đang làm)

Hạ tầng: `db/seed/grammar/*.yaml` → `python3 -m crawler.grammar_seed`.
Mỗi file khai `source` (PDF + số trang) và `entered_by: manual` để truy nguồn.
Ngữ pháp nhập tay **thay thế hoàn toàn** ngữ pháp máy đọc của series đó.

## Xong 3/10 series

| series | nguồn ngữ pháp | ô | option | test |
|---|---|---|---|---|
| **CM2** | máy đọc, PDF trang 6 | 6 | 20 | ✓ |
| **AS** (speed controller) | nhập tay, PDF AS-F trang 7–8 | 7 | 22 | ✓ |
| **TU** (ống PU) | nhập tay, PDF TU trang 2 | 3 | 37 | ✓ |

6/6 test hồi quy pass.

## Chốt được câu hỏi gốc của dự án, có truy nguồn

```
AS2201F-01-06S   ok
   body_size = 2   1/8, 1/4 standard
   shape     = 2   Elbow
   control   = 0   Meter-out
   fitting   = 1F  With One-touch fitting
   port_size = 01  R1/8
   tube_od   = 06  ø6
   sealant   = S   With sealant (AS221F to AS321F)
```
Trùng khớp mã đã tư vấn ở đầu dự án cho `CDM2L32-500Z` — nhưng giờ **đọc ra từ
catalog** chứ không phải từ kiến thức sẵn có. Nguồn: PDF `7-9-3-p0830-0838-AS-F` trang 8
(sơ đồ `AS 2 2 0 1F 01  06 S`), trang 7 có ví dụ `AS2201F-01-04S-X12` xác nhận định dạng.

## Nhập nhằng đã gỡ: hai chữ 'S' khác nghĩa

Trong họ **AS-FS**, chữ `S` đứng ngay sau `1F` là ký hiệu của series (`AS3□□1FS□-□02`),
KHÔNG phải sealant. Sealant là chữ `S` ở **cuối** mã. Nếu encode nhầm sẽ ra mã sai khi
đặt hàng. Đã ghi cảnh báo trong `db/seed/grammar/as.yaml`.

## Lỗi engine đã sửa nhân dịp này

- **Ô bắt buộc thiếu vẫn báo `ok=True`**: `TU0604BU` (thiếu chiều dài cuộn) từng được
  coi là hợp lệ. Giờ trả `ok=False, missing=['roll_length']`.
- **`attrs` chỉ suy được cho xy-lanh**: hardcode bore/stroke/cushion. Giờ gộp `attrs`
  của từng option từ YAML, nên `tube_od_mm`, `port_standard`, `control`… tự có —
  cần cho `part_interface` ở pha C.

## Còn lại 7 series

| series | tình trạng |
|---|---|
| CJ2 | có PDF, spine không khớp — cần đọc tay |
| AC-A (FRL) | có PDF 89 trang — cần đọc tay |
| SY (van) | có PDF 370 trang, 104 trang HTO — nhiều sub-series, nặng nhất |
| D-M9 (cảm biến từ) | PDF chỉ có bản `-5` (2 trang, không phải sơ đồ HTO đầy đủ). Danh sách mã thật nằm trong bảng "Applicable Auto Switches" của PDF CM2 trang 6 — nên trích từ đó |
| AS-FS | biến thể có indicator window, chưa cần cho BOM cơ bản |
| CQ2, KQ2 | **không có PDF** (coverage 31%) — phải tìm nguồn khác |

---

# Pha C — engine BOM (xong bản chạy được)

```
python3 -m engine.cli "CDM2L32-500Z x5"
python3 tests/test_bom.py      # 8 pass
python3 tests/test_parser.py   # 6 pass
```

## Output thật cho 5 xy-lanh

```
TÍNH TOÁN   ø32, cần ø12 (PDF trang 14), hành trình 500
            lực đẩy 402.1 N · lực kéo 345.6 N
            khí/chu kỳ 4.437 L · tổng 887.5 L/min ANR · cần cấp 1331.2 L/min
            tốc độ piston 667 mm/s

BOM         ACTUATOR   CDM2L32-500Z      ×5
            VAN        SY3200-5U1        ×5   [tin cậy 60%]
            ĐƯỜNG ỐNG  TU0604BU-20       ×2   cuộn
            PHỤ KIỆN   AS2201F-01-06S    ×10
            ĐIỆN       D-M9BW            ×10

CẢNH BÁO    ⚠ TUBE_UNDERSIZED — 667 mm/s với ống ø6

CẦN QUYẾT   ? R-MFD-01 đế manifold SS5Y — chưa giải mã được mã
            ? R-FRL-01 bộ FRL — AC-A-E chưa có ngữ pháp
```

Mỗi dòng mang `rule_code` + `rationale` + ghi chú vì sao ghép được
(`R male vào Rc female — chuẩn ISO 7/JIS`), và có `alternatives` khi chọn từ nhiều mã.

## Thành phần

| file | việc |
|---|---|
| `db/seed/interfaces.yaml` | khai giao diện kết nối theo series, giá trị lấy từ attrs / tra bảng / ô mã |
| `engine/materialize.py` | mã hàng → `part` + `part_interface`; `mates()` xét lắp được hay không |
| `engine/generate.py` | chiều ngược của parse: ràng buộc → mã hàng. Không quyết được thì báo, không chọn bừa |
| `engine/calc.py` | lực, khí tiêu thụ, tốc độ piston, kèm `assumptions` |
| `db/seed/rules.yaml` | 8 luật chạy được, mỗi luật có rationale + source |
| `engine/bom.py` | orchestrator 8 bước |
| `engine/cli.py` | in BOM ra terminal |

## Ba lỗi tìm được nhờ chạy thật

**1. Cảnh báo ren giả — nghiêm trọng nhất.** Luật `V-THREAD-01` bản đầu đếm *số chuẩn
ren khác nhau* trong BOM. Nhưng BOM ĐÚNG luôn có nhiều chuẩn: xy-lanh Rc female,
speed controller R male, ren đầu cần M — và `R male vào Rc female là đúng, cố ý`
(ISO 7/JIS). Nên mọi BOM đúng đều bị báo lỗi đỏ. Sửa: đếm **cặp male/female cùng cỡ
mà `thread_compat` nói không lắp được**, và chỉ xét role thuộc đường khí (ren đầu cần
không phải mối nối khí). Có test cả hai chiều: BOM đúng không báo, cặp R→NPT thì báo.

**2. Số cuộn ống cố định = 1.** Sai với 10 đầu one-touch. Sửa: suy từ
`số đầu × 3 m / chiều dài cuộn`, làm tròn lên → 2 cuộn, và ghi rõ trong rationale
rằng 3 m là ƯỚC LƯỢNG cần người dùng chỉnh.

**3. `value_type='literal'` bị check constraint chặn âm thầm.** `insert or ignore`
bỏ qua không báo lỗi nên ô `stroke` mất khỏi ngữ pháp mà không ai biết. Sửa: quy
literal về enum-1-giá-trị và dùng `on conflict do update`.

## Kiểm chứng quan trọng nhất

`test_bore_40_ra_ren_1_4`: nhập `CDM2B40-150AZ` → engine ra `AS2201F-02-06S` (ren 1/4),
không phải `-01` (1/8). Vì cột P của bảng kích thước PDF trang 14 ghi bore 40 → 1/4.
Engine tra theo bore, không giả định một cỡ ren cho cả series.

## Còn lại

| việc | vì sao chưa làm |
|---|---|
| AC-A (FRL) | cần đọc tay PDF 89 trang |
| manifold SS5Y | 104 trang How to Order, nhiều biến thể |
| fitting KQ2, xy-lanh CQ2 | không có PDF (coverage 31%) |
| CJ2 | có PDF, spine không khớp — cần đọc tay |
| Web UI | pha 8 của lộ trình |
| Golden test từ BOM máy cũ | cần file Excel của bạn |
