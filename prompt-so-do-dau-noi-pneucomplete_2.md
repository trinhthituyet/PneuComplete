## 1. Bối cảnh

PneuComplete hiện nhận đầu vào dạng **bảng phẳng**: mỗi dòng là 1 actuator
(mã hàng, số lượng, loại van). Các thiết bị khác (regulator, valve, manifold,
sensor…) được engine tự suy ra từ actuator, hoặc ngư�?i dùng khai riêng ở mục
"Cần bạn khai" — không có khái niệm thiết bị nào **nối vật lý** với thiết bị nào.

Thực tế đấu nối phức tạp hơn nhi�?u so với mô hình 1 actuator → 1 bộ phụ kiện
độc lập. Ví dụ sơ đồ CAD thật (đính kèm tham khảo): 8 cụm valve+cylinder
(push/stopper/gripper) nhưng **toàn bộ dùng chung 1 Filter Regulator và 1 đư�?ng
cấp khí chính**. Bảng phẳng hiện tại không biểu diễn được quan hệ "dùng chung"
này, dẫn đến suy luận BOM có thể sai (nhân đôi regulator, sai cỡ manifold...).

Ngư�?i dùng cũng có nhi�?u thiết bị **không nằm trong 16 series grammar hiện có**
— cần nhập được dưới dạng tự do, không bị chặn bởi parser.

## 2. Mục tiêu

Xây dựng giao diện nhập liệu dạng **sơ đồ khối kết nối** (node-graph editor),
thay thế hoặc bổ sung cho bảng phẳng hiện tại, sao cho:

- Mỗi thiết bị là 1 **khối (node)** gồm: nhóm thiết bị + mã sản phẩm + nhãn tự do.
- Ngư�?i dùng **kéo dây nối** giữa các khối để khai báo quan hệ vật lý/điện.
- Engine đ�?c **toàn bộ đồ thị** (không chỉ từng node riêng lẻ) để suy luận BOM,
  đặc biệt là các thiết bị dùng chung (regulator, manifold, đư�?ng cấp khí).
- Thiết bị không match được grammar vẫn nhập được, ở chế độ "tự do" (manual),
  không bị coi là lỗi.
- Khi engine ch�?n van, phải xét thêm: node đi�?u khiển (PLC) nối với nó, và
  override thủ công ngư�?i dùng gắn trực tiếp lên node/cạnh — ưu tiên cao hơn
  suy luận mặc định.
- �?ồ thị được **lưu lại dạng số hoá (JSON có cấu trúc)** cùng project, không
  chỉ dùng một lần để tính rồi b�?.

**Ràng buộc quan tr�?ng:** dự án này chủ trương "không dùng h�?c máy" (đ�?c
`README.md` gốc) — m�?i suy luận từ đồ thị phải là **rule-based / pattern
matching trên cấu trúc đồ thị**, không phải mô hình h�?c máy.

## 3. Mô hình dữ liệu — Node & Edge

�?�? xuất schema JSON cho 1 đồ thị (gắn với 1 project):

```json
{
  "nodes": [
    {
      "id": "n1",
      "group": "cylinder",
      "code": "CDM2L32-500Z",
      "label": "Push Cylinder for Heat Cluster",
      "qty": 1,
      "manual": false,
      "parsed": { "ok": true, "series": "CDM2", "attrs": { "bore_mm": 32, "stroke_mm": 500 } },
      "overrides": { "valve_function": "double" },
      "ports": [
        { "id": "A", "kind": "pneumatic", "direction": "bidirectional" },
        { "id": "B", "kind": "pneumatic", "direction": "bidirectional" }
      ],
      "position": { "x": 120, "y": 80 }
    },
    {
      "id": "n2",
      "group": "valve",
      "code": null,
      "label": "SV1",
      "manual": false,
      "ports": [
        { "id": "1", "label": "P", "kind": "pneumatic", "direction": "in" },
        { "id": "2", "label": "A", "kind": "pneumatic", "direction": "out" },
        { "id": "4", "label": "B", "kind": "pneumatic", "direction": "out" },
        { "id": "12", "label": "sol", "kind": "electrical", "direction": "in" }
      ],
      "position": { "x": 120, "y": 220 }
    },
    {
      "id": "n3",
      "group": "regulator",
      "code": "AR30-03B-B",
      "label": "Filter Regulator (SMC)",
      "qty": 1,
      "manual": false,
      "ports": [
        { "id": "IN", "kind": "pneumatic", "direction": "in" },
        { "id": "OUT", "kind": "pneumatic", "direction": "out" }
      ],
      "position": { "x": -100, "y": 300 }
    },
    {
      "id": "n9",
      "group": "custom",
      "code": "XYZ-NONSTD-01",
      "label": "Cảm biến tự chế",
      "manual": true,
      "note": "Không thuộc catalog SMC, mua ngoài",
      "ports": [{ "id": "sig", "kind": "electrical", "direction": "out" }],
      "position": { "x": 400, "y": 80 }
    }
  ],
  "edges": [
    { "id": "e1", "from": "n2", "from_port": "2", "to": "n1", "to_port": "A", "kind": "pneumatic_control" },
    { "id": "e2", "from": "n3", "from_port": "OUT", "to": "n2", "to_port": "1", "kind": "pneumatic_supply" }
  ]
}
```

Ghi chú các trư�?ng:

- `group`: enum mở rộng được — `cylinder | valve | regulator | manifold |
  sensor | plc | fitting | tubing | custom | ...` (đ�?c từ danh mục layer hiện
  có trong `bom.py`, bổ sung thêm nhóm mới nếu cần, không hard-code cứng ở UI).
- `code`: mã sản phẩm, có thể `null` nếu chưa xác định hoặc là node "khái niệm"
  (vd valve trong sơ đồ CAD chưa gán mã cụ thể, chỉ có nhãn "SV1").
- `manual: true`: đánh dấu node **không cố gắng parse**, không tính là lỗi
  nếu không hiểu mã. Engine b�? qua node này khi suy luận thông số kỹ thuật,
  nhưng vẫn đưa vào BOM output với qty/label do ngư�?i dùng khai.
- `overrides`: override thủ công tại node, **ưu tiên tuyệt đối** trước khi
  engine tự suy (khác với việc chỉ dùng làm gợi ý).
- `ports`: danh sách cổng kết nối của node — xem chi tiết mục 13 (thư viện
  cổng theo nhóm thiết bị, tái sử dụng `db/seed/interfaces.yaml` đã có).
- `edges[].from_port` / `to_port`: **id cổng cụ thể**, không chỉ nối node với
  node chung chung — cần thiết để engine biết chính xác cổng A hay B của
  cylinder được van nào đi�?u khiển, phát hiện đấu chéo, và validate loại cổng
  (`kind`) có khớp nhau không (pneumatic↔pneumatic, electrical↔electrical).
- `edges[].kind`: loại kết nối, tối thiểu cần phân biệt:
  - `pneumatic_control` — van đi�?u khiển cylinder
  - `pneumatic_supply` — nguồn khí cấp cho valve/manifold (dùng để nhóm
    thiết bị chia sẻ chung 1 regulator/đư�?ng ống)
  - `electrical_signal` — tín hiệu đi�?u khiển từ PLC/controller tới van
  - `mechanical_mount` — quan hệ lắp đặt (vd van gắn lên manifold)
- `position`: toạ độ canvas, chỉ phục vụ vẽ lại, không dùng để suy luận.

## 4. Yêu cầu giao diện (UI/UX)

- Canvas kéo-thả, có **palette bên trái liệt kê nhóm thiết bị bằng chữ**
  (Nguồn & xử lý khí, Van đi�?u khiển, Cơ cấu chấp hành, Cảm biến, PLC,
  Tuỳ chỉnh...) — **không dùng icon hình ảnh minh hoạ cho từng dòng sản
  phẩm**. Lý do: thư viện icon vẽ tay không theo kịp tốc độ mở rộng grammar
  (hiện 16 series, sẽ tăng dần), trong khi engine chỉ cần đúng chuỗi mã hàng
  để tự suy ra toàn bộ thông số — ngư�?i dùng chỉ cần biết đúng **nhóm chức
  năng** của thiết bị, không cần biết trước nó thuộc dòng nào để ch�?n icon.
- Kéo khối nhóm vào canvas → khối hiện ra **rỗng**, có tiêu đ�? = tên nhóm
  (lấy từ `LAYER_VN` đã có), màu khối theo layer (dùng đúng bộ màu hiện có
  trong CSS `index.html`: actuator/valve/air_prep/piping/accessory/
  electrical mỗi loại 1 màu để phân biệt bằng màu thay vì hình ảnh) và 1 ô
  nhập mã hàng bên trong.
- Gõ mã hàng vào khối, blur ra ngoài → g�?i `/api/parse` (đúng cơ chế
  `checkCode()` đang có ở bảng phẳng) → hiện **ngay trong khối**: vi�?n xanh
  + tóm tắt thuộc tính đã parse (bore, stroke...), hoặc vi�?n đ�? + "chưa hiểu
  phần...". Không tra icon nào — chỉ đổi trạng thái/màu vi�?n + text.
- Click vào node mở **panel chi tiết** (giống dạng "Cần bạn khai" hiện tại):
  số lượng, overrides, hoặc bật "chế độ tự do" nếu mã không thuộc catalog —
  khối vẫn giữ nguyên hình dạng, chỉ đổi vi�?n sang màu trung tính, không báo lỗi.
- Vẽ dây nối bằng cách kéo từ cạnh node này sang node khác; khi thả, h�?i loại
  kết nối (`pneumatic_control`/`pneumatic_supply`/`electrical_signal`/
  `mechanical_mount`) qua menu nh�? hoặc suy đoán mặc định theo cặp nhóm
  thiết bị (vd valve→cylinder mặc định là `pneumatic_control`).
- Vẫn giữ khả năng **nhập nhanh dạng danh sách** (paste nhi�?u mã hàng) để tạo
  hàng loạt node cylinder cùng lúc — sau đó ngư�?i dùng vẽ dây nối thêm, tránh
  ép buộc vẽ hoàn toàn thủ công từng node một.
- Nút "Dựng BOM" gửi toàn bộ đồ thị (`nodes` + `edges`) lên backend thay vì
  danh sách phẳng.

## 5. Yêu cầu backend/engine

- API `/api/bom` nhận thêm payload dạng đồ thị (giữ tương thích ngược với
  payload phẳng cũ nếu có thể, hoặc versioning endpoint).
- Thêm bước **graph resolver** trong `engine/bom.py` trước khi chạy rule engine
  hiện có:
  - Gom nhóm các node chia sẻ chung nguồn cấp khí (theo cạnh `pneumatic_supply`)
    → tránh nhân đôi regulator/FRL khi nhi�?u valve dùng chung 1 nguồn.
  - Map van → cylinder theo cạnh `pneumatic_control` thay vì suy đoán 1-1
    theo thứ tự nhập.
  - Với node có cạnh `electrical_signal` tới 1 node `plc`: đ�?c thuộc tính của
    node PLC (điện áp, loại connector, loại tín hiệu — cần định nghĩa thêm
    trong catalog "plc"/"controller") làm **đầu vào bổ sung** cho luật ch�?n
    van (`rules.yaml`), không chỉ dựa specs actuator.
  - **Validate loại cổng khi nối** (`from_port`/`to_port`, mục 3 & 13): nếu
    `ports[].kind` của 2 đầu không khớp (vd nối `electrical` vào `pneumatic`)
    → sinh cảnh báo qua đúng cơ chế `warnings` hiện có (`severity`,
    `rule_code`, `rationale`), không chặn cứng nhưng phải hiện rõ.
  - Override tại node (`overrides`) luôn thắng luật mặc định.
- Node `manual: true` không parse, không sinh cảnh báo/gap v�? "chưa hiểu mã",
  chỉ đưa thẳng vào BOM output ở layer tương ứng với `group` đã ch�?n (nếu
  `group` không khớp layer nào có sẵn, đưa vào layer `other`).
- Lưu đồ thị: mở rộng schema DB — thêm bảng hoặc cột JSON gắn với `project`
  hiện có (vd `project_graph(project_id, graph_json)`), để:
  - Xem lại sơ đồ của các project cũ (kết hợp với giới hạn 200 project gần
    nhất hiện có).
  - V�? sau có thể dùng đồ thị đã lưu để dò **pattern kết nối lặp lại** (rule
    thống kê, không phải ML) — vd "80% project có group gripper luôn nối
    electrical_signal tới cùng loại PLC X" → gợi ý mặc định, không tự động áp.

## 6. Thiết bị "tự do" (không theo grammar)

- Ngư�?i dùng bật c�? "mã tự do" trên bất kỳ node nào.
- UI không g�?i `/api/parse` cho node này, không hiện vi�?n đ�?/xanh, chỉ yêu
  cầu tối thiểu: nhóm thiết bị + nhãn + số lượng.
- BOM output vẫn liệt kê node này (để không sót thiết bị), nhưng rõ ràng đánh
  dấu "nhập tay, không qua kiểm tra kỹ thuật" — tránh nhầm với dòng do engine
  tự suy luận có `rule_code`/`rationale`.

## 7. Số hoá đồ thị kỹ thuật trong catalog (vấn đ�? riêng — bắt buộc)

Khác với sơ đồ đấu nối ở mục 3–6 (mô tả **thiết bị nào liên quan tới thiết bị
nào**), đây là việc số hoá **đồ thị kỹ thuật in trong catalog PDF** của nhà
sản xuất — ví dụ đồ thị lưu lượng theo áp suất, đư�?ng cong Cv, biểu đồ ch�?n
cỡ FRL theo tổng lưu lượng, đư�?ng cong lực đẩy/kéo. Hiện các giá trị này nằm
trong `NEEDS_INPUT` (`server.py`) — `main_line_port_size`, `frl_size`,
`valve_series_size` — đúng lý do ghi trong code: *"catalog chỉ cho lưu lượng
dạng đồ thị"*, *"engine chưa trích được Cv từ catalog"*. Hai việc (đấu nối +
đồ thị catalog) độc lập nhưng bổ trợ nhau: graph resolver dùng topology để
biết **nhóm thiết bị nào cần tính chung 1 giá trị** (vd tổng lưu lượng của các
valve chia sẻ 1 regulator), rồi tra cứu đồ thị đã số hoá để **suy ra giá trị
đó thay vì h�?i ngư�?i dùng**.

### Vì sao cần thiết

Nếu số hoá được các đồ thị này thành dữ liệu có cấu trúc (tập điểm lấy mẫu),
engine tự tra cứu giá trị chính xác thay vì bắt ngư�?i dùng đ�?c catalog thủ
công rồi gõ vào — giảm số mục "Cần bạn khai", tăng độ chính xác, và giữ đúng
nguyên tắc hiện có của dự án: **không đoán bừa, m�?i giá trị đ�?u có nguồn trích
dẫn và độ tin cậy**.

### Mô hình dữ liệu đ�? xuất

Theo đúng pattern đã có (`db/seed/grammar/*.yaml` cho ngữ pháp mã hàng,
`db/seed/rules.yaml` có `rationale` + `source` cho mỗi luật) — thêm thư mục
mới, ví dụ `db/seed/charts/*.yaml`, mỗi tệp là 1 đồ thị đã số hoá:

```yaml
chart_id: sy_flow_vs_bore
title: "Lưu lượng danh định theo cỡ van SY3000/5000/7000"
source:
  catalog: SY_valve_catalog.pdf
  page: 42
  figure: "Fig. 3"
axis:
  x: { name: port_size_mm, unit: mm }
  y: { name: flow_lpm, unit: "L/min ANR" }
series:
  - label: SY3000
    points: [[4, 300], [6, 450], [8, 600]]
  - label: SY5000
    points: [[6, 800], [8, 1100], [10, 1400]]
digitized_by: "tên ngư�?i nhập, ngày"
confidence: 0.9   # đ�?c điểm từ ảnh nên không tuyệt đối chính xác
```

- `points`: tập điểm lấy mẫu bằng cách click trên ảnh đồ thị (xem công cụ số
  hoá bên dưới); engine **nội suy tuyến tính** giữa các điểm khi cần giá trị
  trung gian, và **không ngoại suy** ra ngoài khoảng đã số hoá (ngoài khoảng
  → vẫn báo gap, giữ nguyên tắc không đoán bừa).
- `source` + `confidence`: bám sát cơ chế đang có của `rules.yaml`, để không
  phá vỡ tính minh bạch (mỗi dòng BOM đ�?u có lý do + độ tin cậy).
- `series`: 1 đồ thị có thể chứa nhi�?u đư�?ng cong (theo cỡ van, theo áp suất...).
- Nên đánh dấu `manual`/bảo vệ kh�?i bị ghi đè tự động, giống cách
  `series.grammar_source: 'manual'` đang được bảo vệ kh�?i parser máy.

### Công cụ số hoá (nội bộ, không phải tính năng cho end-user)

Vì catalog chỉ có PDF/ảnh, cần công cụ nội bộ (cùng nhóm với
`crawler/grammar_seed.py` hiện có) để ngư�?i phụ trách:

1. Mở ảnh trang catalog (đã có sẵn trong `cache/` do crawler tải).
2. Click 2 điểm mốc trên mỗi trục để **calibrate** tỉ lệ pixel → giá trị thật.
3. Click từng điểm dữ liệu trên đư�?ng cong (giao diện web đơn giản: ảnh +
   canvas overlay).
4. Xuất YAML theo schema trên, lưu vào `db/seed/charts/`.

### Engine sử dụng dữ liệu đồ thị

- Thêm hàm tra cứu kiểu `chart.lookup(chart_id, x_value) -> (y_value, note)`.
- Thay vì bắt buộc ngư�?i dùng khai `main_line_port_size`/`frl_size`/
  `valve_series_size`, engine tự tính tổng lưu lượng hệ thống (đã có sẵn
  `system.total_flow_lpm` trong `bom.py`) rồi g�?i `chart.lookup(...)` để tự đ�?
  xuất — **chỉ h�?i ngư�?i dùng khi giá trị tính được nằm ngoài khoảng đã số
  hoá** (tránh ngoại suy sai).
- Kết quả tra cứu phải hiện `rationale` giống các luật khác, ví dụ:
  `"R-FRL-02: tra Fig.3 trang 42 (SY_valve_catalog.pdf), lưu lượng hệ thống
  850 L/min → FRL cỡ 20 (nội suy 2 điểm đã số hoá, độ tin cậy 90%)"`.

## 8. Test case chấp nhận (dựa theo sơ đồ CAD gửi kèm)

Dựng lại đúng cấu trúc trong hình CAD tham khảo: 8 cụm van+cylinder (2 push,
2 stopper, 2 gripper, 2 push khác) nối chung tới 1 node Filter Regulator qua
`pneumatic_supply`. Kỳ v�?ng:

- BOM chỉ có **1 dòng Filter Regulator** (không nhân theo số cylinder).
- 8 dòng valve, mỗi dòng có `rationale` tham chiếu đúng cylinder nó đi�?u khiển
  (lấy từ cạnh `pneumatic_control`, không phải suy đoán tuần tự).
- Nếu 1 trong 8 valve có cạnh `electrical_signal` tới node PLC có điện áp
  24VDC → dòng đ�? xuất coil van phải khớp 24VDC, có ghi rõ lý do lấy từ node
  PLC trong `rationale`.
- Thêm 1 node `custom` (manual) bất kỳ → xuất hiện trong BOM ở layer phù hợp,
  không sinh cảnh báo "chưa hiểu mã".

## 9. Triển khai theo giai đoạn (đ�? xuất)

1. **Data model + persist đồ thị đấu nối**: thêm schema đồ thị, lưu DB, API
   nhận/trả graph — chưa cần UI vẽ, có thể test qua JSON thô trước.
2. **Số hoá đồ thị catalog (mục 7)**: xây công cụ nội bộ + số hoá trước 3–5
   đồ thị đang gây "Cần bạn khai" nhi�?u nhất (`frl_size`, `valve_series_size`)
   — làm song song, không phụ thuộc UI canvas, có thể tách nhóm phụ trách riêng.
3. **Canvas UI**: trình soạn kéo-thả + vẽ dây, thay thế dần bảng phẳng (có
   thể giữ song song bảng phẳng cho nhập nhanh nhi�?u cylinder).
4. **Graph resolver trong engine**: xử lý nhóm dùng chung nguồn cấp, map
   van↔cylinder theo cạnh, g�?i `chart.lookup()` khi cần giá trị định lượng
   cho cả nhóm.
5. **Suy luận van có ngữ cảnh PLC + override**: mở rộng `rules.yaml`/logic
   ch�?n van để nhận thêm input từ node liên kết.
6. **Node tự do (manual) end-to-end**: từ UI tới BOM output tới CSV export.

## 10. Trình tự thao tác (workflow 5 bước)

�?�? xuất tổ chức UI theo 5 trạng thái sau (không phải wizard khoá cứng — xem
lưu ý bên dưới):

1. **Soạn sơ đồ** — canvas kéo-thả node + vẽ dây (mục 4).
2. **Phân tích tự động** — validate từng node (vi�?n xanh/đ�?) + chạy graph
   resolver (mục 5): gom nhóm dùng chung nguồn cấp, map van↔cylinder theo
   cạnh, g�?i `chart.lookup()` (mục 7) để tra giá trị định lượng.
3. **Câu h�?i cần thiết** — bản động của "Cần bạn khai" hiện tại: chỉ h�?i đúng
   những gì bước 2 xác định là **thật sự thiếu** sau khi đã thử tra đồ thị
   catalog, không phải danh sách cố định 6 mục như UI hiện tại.
4. **Thiết bị đ�? xuất** — hiển thị kết quả rule engine + chart lookup dưới
   dạng **preview có thể duyệt/sửa/ghi đè** trước khi chốt, giữ đúng nguyên
   tắc hiện có *"đây là bản đ�? xuất, không phải bản chốt"*.
5. **Kết quả & BOM** — ngoài bảng BOM theo layer (như hiện tại), render lại
   chính sơ đồ đã vẽ ở bước 1 với mã hàng đã ch�?n chú thích trực tiếp trên
   từng node, không chỉ liệt kê tách r�?i dạng text.

**Lưu ý quan tr�?ng:** không nên khoá tuyến tính "next/back". Công việc thực
tế lặp lại (sửa sơ đồ sau khi thấy BOM, thêm thiết bị sau khi có cảnh báo...).
5 nút trạng thái nên **click được tự do**, bước nào phụ thuộc dữ liệu vừa đổi
ở bước trước thì tự đánh dấu "cần chạy lại" thay vì ép ngư�?i dùng đi tuần tự.

### Thanh công cụ vẽ sơ đồ

Bộ công cụ tối thiểu: Ch�?n · Dây · Gán nhãn · Xoá · Căn chỉnh · zoom/fit.
Bổ sung thêm để khớp schema đã thiết kế:

- **Hoàn tác/Làm lại** (undo/redo).
- Khi ch�?n công cụ **Dây**, cần menu phụ ch�?n `edges[].kind` (mục 3) —
  `pneumatic_control` / `pneumatic_supply` / `electrical_signal` /
  `mechanical_mount` — nếu không ch�?n, engine không phân biệt được "van đi�?u
  khiển cylinder" với "van dùng chung nguồn cấp".
- **Nhân bản node** — cần khi có nhi�?u cụm giống hệt nhau (vd 8 trạm van
  trong sơ đồ CAD tham khảo).
- Nút bật nhanh **"mã tự do"** (`manual: true`, mục 6) ngay trên node đang
  ch�?n, không cần mở panel chi tiết mỗi lần.

## 11. Quyết định đã chốt

- **Không import CAD/DXF.** Toàn bộ sơ đồ đấu nối được vẽ tay hoàn toàn trong
  phần m�?m (canvas kéo-thả + vẽ dây, mục 4/10) — không có pipeline đ�?c file
  CAD ngoài. �?i�?u này loại b�? nhu cầu xử lý geometry/DXF ra kh�?i phạm vi dự
  án; các sơ đồ CAD tham khảo (như ảnh gửi kèm) chỉ dùng để đối chiếu bố cục
  khi thiết kế UI/test case, không phải nguồn dữ liệu đầu vào thực tế.

## 12. Cơ chế vẽ dây nối

So sánh 2 giải pháp tương tác phổ biến:

| | Kéo-thả (drag wire) | Bấm điểm đầu → điểm cuối (click-click) |
|---|---|---|
| Cách dùng | Giữ chuột tại cổng nguồn, kéo tới cổng đích, thả | Bấm cổng nguồn (vào "chế độ đang nối"), bấm cổng đích để hoàn tất |
| Ưu điểm | Trực quan, nhanh, quen thuộc (draw.io, Miro, Figma connector) | Chính xác hơn khi sơ đồ dày đặc, pan/zoom được giữa 2 lần bấm để nhắm đúng cổng, thân thiện bút cảm ứng — đúng phong cách phần m�?m CAD điện/khí nén chuyên dụng (EPLAN, AutoCAD Electrical, KiCad) |
| Nhược điểm | Dễ nối nhầm cổng li�?n k�? khi sơ đồ dày đặc (vd sơ đồ 8-valve tham khảo), khó dùng trên trackpad | Cần chỉ dấu rõ ràng "đang ở chế độ nối" để không nhầm với thao tác ch�?n/di chuyển node |

**�?�? xuất: hỗ trợ cả hai, dùng chung 1 vùng thao tác** (không bắt ch�?n tool
riêng trước khi vẽ):

1. Hover lên 1 cổng (`ports[]`, mục 3) → cổng sáng lên, con tr�? đổi thành "+".
2. Bấm nhẹ (không kéo) vào cổng nguồn → vào **chế độ đang nối** (dây bám theo
   con tr�?, cho phép pan/zoom giữa chừng để tìm đúng cổng đích).
3. Bấm cổng đích → hoàn tất, tự mở menu nh�? ch�?n `edges[].kind` hoặc suy đoán
   mặc định theo cặp `group`/`ports[].kind` (vd valve→cylinder qua cổng
   pneumatic mặc định là `pneumatic_control`).
4. Nếu ngư�?i dùng **kéo** thay vì bấm-thả ngay (phát hiện qua khoảng cách di
   chuột trước khi nhả) → tự chuyển sang kéo-thả, thả đúng cổng đích là nối
   luôn — 2 cơ chế dùng chung, không phải 2 tool tách biệt.
5. Esc hoặc bấm vùng trống → huỷ đang nối.

Lý do ch�?n click-click làm mặc định: đối tượng dùng là kỹ sư vẽ sơ đồ kỹ
thuật chi tiết, độ chính xác quan tr�?ng hơn tốc độ vẽ nhanh — kéo-thả vẫn giữ
làm lối tắt cho thao tác quen tay.

## 13. Thư viện thiết bị có thuộc tính & cổng kết nối (ports)

### Template nhóm thiết bị (device group template)

Mỗi `group` cần định nghĩa sẵn:

- **Danh sách cổng mặc định** (`ports`, mục 3): id, nhãn, loại
  (`pneumatic`/`electrical`/`mechanical`), hướng (`in`/`out`/`bidirectional`).
  - Cylinder: cổng A, B (pneumatic, bidirectional).
  - Van 5/2: cổng 1/P (in), 2·4/A·B (out), 3·5/R·S (xả, out), 12·14 (tín hiệu
    đi�?u khiển, in).
  - Regulator: cổng IN, OUT.
- **Thuộc tính mặc định theo nhóm** (không phải riêng từng mã) — vd nhóm "van
  đi�?u khiển" mặc định có field điện áp coil, kiểu đấu điện.

**Quan tr�?ng — tránh làm trùng lặp:** repo đã có sẵn `db/seed/interfaces.yaml`,
README mô tả đây là *"Template cửa/ren cho từng h�? — n�?n tảng của suy luận"*
— gần như chính xác là dữ liệu cổng cần dùng cho canvas. Việc cần làm là
**kiểm tra cấu trúc hiện có của file này và ánh xạ sang `ports`**, không viết
schema song song mới từ đầu.

### Thư viện do ngư�?i dùng tự tạo (custom template)

- Khi ngư�?i dùng tạo 1 node "tự do" (`manual: true`, mục 6) nhi�?u lần với
  cùng cấu hình (vd 1 loại cảm biến hay dùng, không thuộc catalog SMC) → cho
  phép **"Lưu làm mẫu"** ngay từ panel chi tiết node.
- Mẫu tự tạo lưu riêng (vd bảng `user_templates`), có nhãn nhóm tự đặt, cổng
  tự định nghĩa (thêm điểm cổng lên khối), thuộc tính tự đặt tên.
- Hiện trong palette ở mục riêng **"Thư viện của tôi"**, tách biệt rõ kh�?i
  thư viện chính thức (đến từ catalog SMC đã crawl) — tránh nhầm dữ liệu có
  nguồn gốc catalog (đáng tin, có `source`/`confidence`) với dữ liệu tự khai
  (không kiểm chứng).
- Mẫu tự tạo không có `rule_code`/`rationale` tự động — BOM output đánh dấu
  rõ nguồn "mẫu ngư�?i dùng tự tạo", nhất quán với cách xử lý node `manual`.

### Engine dùng cổng để làm gì

- Validate loại cổng khi nối dây (mục 5) — cảnh báo nếu nối sai loại
  (`electrical` vào `pneumatic`), theo đúng cơ chế `warnings` hiện có.
- Biết chính xác **cổng nào** được nối (không chỉ node nào) → phát hiện đấu
  chéo A/B, và có thêm dữ kiện để tính chi�?u hoạt động chính xác hơn khi tính
  lực đẩy/kéo (liên hệ khối "Tính toán" đang có trong `render()` của
  `index.html`).

## 14. Câu h�?i cần làm rõ trước khi code

- Cạnh nối có cần thể hiện **hướng dòng khí** (nguồn → tải) hay chỉ cần "có
  liên kết, không phân hướng"?
- Override tại node có cho phép ghi đè **toàn bộ** kết quả 1 dòng BOM (thay
  thế hẳn phần đ�? xuất của engine) hay chỉ ảnh hưởng 1 vài thuộc tính?
- Giới hạn số lượng node/edge tối đa mỗi sơ đồ (ảnh hưởng hiệu năng canvas)?
- Nhóm thiết bị mới (vd `plc`, `sensor`, `custom`) có cần thêm layer riêng
  trong BOM output (`LAYER_VN` trong `index.html`) hay gộp vào layer hiện có?
- Ai chịu trách nhiệm số hoá đồ thị catalog (mục 7) — cùng ngư�?i đang duyệt
  `db/seed/grammar/*.yaml` hay cần vai trò riêng? Việc này tốn công thủ công
  nên cần ưu tiên đồ thị nào trước (gợi ý: bắt đầu từ các đồ thị đang chặn
  nhi�?u `NEEDS_INPUT` nhất).
- Khi giá trị cần tra nằm **ngoài khoảng đã số hoá**, có chấp nhận nội suy
  tuyến tính "an toàn" (vd ngoại suy ±10%) hay tuyệt đối không, chỉ báo gap?
