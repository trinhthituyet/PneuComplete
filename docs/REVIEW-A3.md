# Phiếu duyệt A3 — dữ liệu cần bạn xác nhận

Sinh tự động từ DB thật (`python3 -m crawler.review sheet`). Ước lượng 1 giờ.

Mục đích: 4 series đã có ngữ pháp đều do tôi đọc PDF, chưa ai kiểm. Trước khi mở rộng thêm series (giai đoạn B), cần biết cái đang có có đúng không — nếu không thì mở rộng chỉ nhân rộng cái sai.

Ghi quyết định:
```
python3 -m crawler.review ok A3-1
python3 -m crawler.review no A3-1 "cột D là đường kính ngoài ống, không phải cần"
```


## Phần 1 — CẦN XÁC NHẬN (ưu tiên theo rủi ro)


### [ ] A3-1 · rủi ro cao · `engine/calc.py rod_dia_mm`

**Tôi đang dùng:** Cột 'D' của bảng kích thước PDF CM2 trang 14 là ĐƯỜNG KÍNH CẦN: bore 20→ø8, 25→ø10, 32→ø12, 40→ø14

- ✅ đọc được từ catalog: Số liệu đọc trực tiếp từ bảng (map cột theo toạ độ header, D ở x=122)
- ⚠️ phần tôi suy: Việc cột 'D' nghĩa là đường kính cần — tôi không xem được bản vẽ. Bản trước tôi ghi bore 40 → ø16 theo trí nhớ, bảng thật ghi 14.
- 💥 nếu sai: Sai → LỰC KÉO tính sai (lực đẩy không ảnh hưởng). Với ø40 chênh 551 N vs 503 N nếu thực tế là ø16.
- ❓ cách kiểm: Mở PDF CM2 trang 14, xem bản vẽ: ký hiệu D trỏ vào đường kính cần hay kích thước khác?

### [ ] A3-2 · rủi ro cao · `db/seed/grammar/d-m9.yaml`

**Tôi đang dùng:** Quy ước đặt tên D-M9: N=3-wire NPN, P=3-wire PNP, B=2-wire, W=2-color indicator, A=water resistant, V=perpendicular entry

- ✅ đọc được từ catalog: 38 mã (M9N, M9BW, A93V…) đọc trực tiếp từ bảng Applicable Auto Switches, PDF CM2 trang 6. Chiều dài dây Nil/M/L/Z cũng đọc trực tiếp.
- ⚠️ phần tôi suy: Ý nghĩa từng chữ cái — tôi đối chiếu với các dòng của bảng ('3-wire (NPN)', '2-wire', 'Diagnostic indication (2-color)') nhưng bảng bị -layout làm sập nên không khớp được từng ô chắc chắn.
- 💥 nếu sai: Sai → engine chọn sai loại cảm biến. Ví dụ cần PNP mà ra NPN thì không đọc được tín hiệu vào PLC.
- ❓ cách kiểm: Với xy-lanh CM2, cảm biến D-M9BW có đúng là 2-wire, 2-color indicator, ra dây thẳng (grommet) không?

### [ ] A3-3 · rủi ro trung bình · `db/seed/grammar/tu.yaml`

**Tôi đang dùng:** Mã ống TU0425 nghĩa là OD ø4 / ID ø2.5; TU0604 = OD6/ID4; TU0805 = OD8/ID5; TU1065 = OD10/ID6.5; TU1208 = OD12/ID8

- ✅ đọc được từ catalog: Danh sách mã TU0425/TU0604/TU0805/TU1065/TU1208 đọc từ bảng 'Made to Order Availability', PDF TU trang 2.
- ⚠️ phần tôi suy: Cách giải nghĩa 4 chữ số thành OD/ID — theo quy ước, không đọc được bảng OD/ID tường minh trong 2 trang PDF này.
- 💥 nếu sai: Sai → chọn ống sai cỡ, không cắm được vào đầu one-touch ø6.
- ❓ cách kiểm: Ống TU0604 có đúng là ngoài ø6, trong ø4 không?

### [ ] A3-4 · rủi ro trung bình · `db/seed/grammar/d-m9.yaml`

**Tôi đang dùng:** Ký hiệu chiều dài dây 'N' = không có dây (loại connector)

- ✅ đọc được từ catalog: Chú thích PDF CM2 trang 6 có dãy '(Nil) (M) (L) (Z) (N)' và ghi rõ 0.5m=Nil, 1m=M, 3m=L, 5m=Z.
- ⚠️ phần tôi suy: Riêng 'N' không có chú thích chiều dài → tôi suy là 'không dây'.
- 💥 nếu sai: Thấp — engine mặc định dùng Nil (0.5 m), không tự chọn N.
- ❓ cách kiểm: Bỏ qua được nếu bạn không dùng loại connector.

### [ ] A3-5 · rủi ro trung bình · `db/seed/rules.yaml R-TUBE-01`

**Tôi đang dùng:** Mỗi đầu one-touch cần ~3 m ống → 10 đầu = 30 m = 2 cuộn 20 m

- ✅ đọc được từ catalog: Không đọc từ đâu cả.
- ⚠️ phần tôi suy: Con số 3 m là tôi đặt ra làm mặc định. Engine đã ghi rõ trong rationale rằng đây là ƯỚC LƯỢNG.
- 💥 nếu sai: Sai → thiếu hoặc thừa ống. Không nguy hiểm nhưng lệch chi phí.
- ❓ cách kiểm: Với máy của bạn, trung bình mỗi mối nối cần bao nhiêu mét ống?

### [ ] A3-6 · rủi ro thấp · `engine/bom.py ctx['acting']`

**Tôi đang dùng:** CM2 là xy-lanh tác động 2 chiều (double acting) — engine gán cứng

- ✅ đọc được từ catalog: Bảng variation HTML của trang series CM2 ghi 'Double acting, Single rod' và 'Single acting (Spring return/extend)' — CÓ CẢ HAI loại.
- ⚠️ phần tôi suy: Engine đang gán cứng 'double' cho mọi mã CM2. Mã CM2 loại single acting có ký hiệu riêng mà ngữ pháp hiện tại chưa phân biệt.
- 💥 nếu sai: Nhập mã xy-lanh single-acting → engine vẫn đề xuất 2 speed controller và van 5/2, trong khi chỉ cần 1 và van 3/2.
- ❓ cách kiểm: Bạn có dùng xy-lanh single acting (hồi lò xo) không? Nếu có thì đây là lỗi cần sửa trước khi dùng thật.

### [ ] A3-7 · rủi ro thấp · `db/seed/interfaces.yaml CM2 rod_end`

**Tôi đang dùng:** Ren đầu cần: bore 20→M8x1.25, 25→M10x1.25, 32→M10x1.25, 40→M14x1.5

- ✅ đọc được từ catalog: ĐỌC TRỰC TIẾP cột MM của bảng kích thước PDF trang 14. Cả 4 giá trị.
- ⚠️ phần tôi suy: Không suy gì. Chỉ cần bạn xác nhận cột 'MM' là ren đầu cần.
- 💥 nếu sai: Sai → chọn sai joint/knuckle đầu cần (chưa có trong BOM hiện tại).
- ❓ cách kiểm: Xem bản vẽ trang 14: MM có phải ren đầu cần?


## Phần 2 — Ngữ pháp đang dùng (đối chiếu nhanh với catalog)


### AS  (`AS-E-E`)
nguồn: | ngữ pháp nhập tay từ as.yaml: PDF 7-9-3-p0830-0838-AS-F_en.pdf, trang 7-8 | ngữ pháp nhập tay từ as.yaml: PDF 7-9-3-p0830-0838-AS-F_en.pdf, trang 7-

- **ô 1 body_size** (enum) — 4 lựa chọn
    - `1` = M3, M5 standard
    - `2` = 1/8, 1/4 standard
    - `3` = 3/8
    - `4` = 1/2
- **ô 2 shape** (enum) — 2 lựa chọn
    - `2` = Elbow
    - `3` = Universal
- **ô 3 control** (enum) — 2 lựa chọn
    - `0` = Meter-out
    - `1` = Meter-in
- **ô 4 fitting** (enum) — 1 lựa chọn
    - `1F` = With One-touch fitting
- **ô 5 port_size** (enum, ngăn cách `-`) — 5 lựa chọn
    - `M5` = M5 x 0.8
    - `01` = R1/8
    - `02` = R1/4
    - `03` = R3/8
    - `04` = R1/2
- **ô 6 tube_od** (enum, ngăn cách `-`) — 5 lựa chọn
    - `04` = ø4
    - `06` = ø6
    - `08` = ø8
    - `10` = ø10
    - `12` = ø12
- **ô 7 sealant** (enum) — 3 lựa chọn
    - `Nil` = Without sealant
    - `S` = With sealant (AS221F to AS321F)
    - `SN` = With sealant (AS421F only)

### CM2/CDM2-Z  (`CM2-CDM2-Z-E`)
- **ô 1 mounting** (enum) — 13 lựa chọn
    - `B` = Basic (Double-side bossed)
    - `T` = Head trunnion
    - `L` = Axial foot
    - `E` = Integrated clevis *
    - `F` = Rod flange
    - `V` = Integrated clevis (90°)
    - `G` = Head flange
    - `BZ` = Boss-cut/Basic
    - `C` = Single clevis
    - `FZ` = Boss-cut/Rod flange
    - `D` = Double clevis
    - `UZ` = Boss-cut/Rod trunnion
    - `U` = Rod trunnion
- **ô 2 bore** (enum) — 4 lựa chọn
    - `20` = mm
    - `25` = mm
    - `32` = mm
    - `40` = mm
- **ô 3 stroke** (integer, ngăn cách `-`) — 0 lựa chọn
- **ô 4 cushion** (enum) — 2 lựa chọn
    - `Nil` = Rubber bumper
    - `A` = Air cushion
- **ô 5 series_suffix** (enum) — 1 lựa chọn
    - `Z` = giá trị cố định của series
- **ô 6 auto_switch** (free) — 0 lựa chọn

### D-M9  (`D-M9-CM2-E`)
nguồn: PDF 7-3-2-p0231-0332-CM2_en.pdf, trang 6, bảng Applicable Auto Switches | ngữ pháp nhập tay từ d-m9.yaml: PDF 7-3-2-p0231-0332-CM2_en.pdf, trang 6, bả

- **ô 1 model** (enum, ngăn cách `-`) — 35 lựa chọn
    - `M9N` = 3-wire NPN, grommet
    - `M9NV` = 3-wire NPN, perpendicular entry
    - `M9NW` = 3-wire NPN, 2-color indicator
    - `M9NWV` = 3-wire NPN, 2-color, perpendicular
    - `M9NA` = 3-wire NPN, water resistant (2-color)
    - `M9NAV` = 3-wire NPN, water resistant, perpendicular
    - `M9P` = 3-wire PNP, grommet
    - `M9PV` = 3-wire PNP, perpendicular entry
    - `M9PW` = 3-wire PNP, 2-color indicator
    - `M9PWV` = 3-wire PNP, 2-color, perpendicular
    - `M9PA` = 3-wire PNP, water resistant (2-color)
    - `M9PAV` = 3-wire PNP, water resistant, perpendicular
    - `M9B` = 2-wire, grommet
    - `M9BV` = 2-wire, perpendicular entry
    - … còn 21 lựa chọn nữa
- **ô 2 lead_wire** (enum) — 5 lựa chọn
    - `Nil` = 0.5 m
    - `M` = 1 m
    - `L` = 3 m
    - `Z` = 5 m
    - `N` = không có dây (loại connector)

### TU  (`TU-E`)
nguồn: | ngữ pháp nhập tay từ tu.yaml: PDF 7-9-2-p0682-0683-TU-TIUB_en.pdf, trang 2 | ngữ pháp nhập tay từ tu.yaml: PDF 7-9-2-p0682-0683-TU-TIUB_en.pdf, tran

- **ô 1 model** (enum) — 5 lựa chọn
    - `0425` = OD ø4 / ID ø2.5
    - `0604` = OD ø6 / ID ø4
    - `0805` = OD ø8 / ID ø5
    - `1065` = OD ø10 / ID ø6.5
    - `1208` = OD ø12 / ID ø8
- **ô 2 color** (enum) — 29 lựa chọn
    - `B` = Black (Opaque)
    - `W` = White (Opaque)
    - `R` = Red (Translucent)
    - `BU` = Blue (Translucent)
    - `Y` = Yellow (Opaque)
    - `G` = Green (Opaque)
    - `C` = Clear (Material color)
    - `YR` = Orange (Opaque)
    - `BU1` = Solid blue (Opaque)
    - `BU2` = Clear blue (Translucent)
    - `BU3` = Medium blue (Opaque)
    - `BR1` = Brown (Opaque)
    - `G1` = Solid green (Opaque)
    - `G2` = Clear green (Translucent)
    - … còn 15 lựa chọn nữa
- **ô 3 roll_length** (enum, ngăn cách `-`) — 3 lựa chọn
    - `20` = cuộn 20 m
    - `100` = cuộn 100 m
    - `200` = cuộn 200 m


## Phần 3 — Mã engine sinh ra, kiểm bằng mắt

| mã | nghĩa engine hiểu |
|---|---|
| `CDM2L32-500Z` | bore_mm=32.0, stroke_mm=500, has_magnet=True, cushion=rubber_bumper |
| `CDM2B40-150AZ` | bore_mm=40.0, stroke_mm=150, has_magnet=True, cushion=air |
| `AS2201F-01-06S` | body_size=2, port_sizes=['1/8', '1/4'], shape=elbow, control=meter_out, fitting=one_touch, port_standard=R, port_size=1/8, tube_od_mm=6.0, sealant=True |
| `AS2201F-02-06S` | body_size=2, port_sizes=['1/8', '1/4'], shape=elbow, control=meter_out, fitting=one_touch, port_standard=R, port_size=1/4, tube_od_mm=6.0, sealant=True |
| `TU0604BU-20` | tube_od_mm=6.0, tube_id_mm=4.0, roll_length_m=20 |
| `D-M9BW` | wiring=2-wire, indicator=2-color, entry=grommet, water_resistant=False, lead_wire_m=0.5 |