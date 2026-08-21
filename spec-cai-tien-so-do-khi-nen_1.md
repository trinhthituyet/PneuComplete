# SPEC: Cải tiến Node Editor sơ đồ hệ thống khí nén

> Prompt/spec này dùng để đưa cho dev hoặc AI coding agent implement lại engine vẽ sơ đồ + logic ch�?n van.

---

## 1. �?ư�?ng nối (connector): Spline → Orthogonal (right-angle routing)

**Hiện trạng:** đư�?ng nối giữa các cổng đang là spline (cong tự do), không g�?n, khó đ�?c theo chuẩn P&ID.

**Yêu cầu:**
- Thay thuật toán vẽ line từ Bezier/spline sang **orthogonal routing** (kiểu "elbow connector" — chỉ gồm các đoạn ngang/d�?c vuông góc, giống Visio/draw.io/Lucidchart).
- Thuật toán tối thiểu cần:
  1. Xác định điểm xuất phát (source port) và điểm đích (target port), cùng hướng thoát mặc định của mỗi cổng (ví dụ cổng bên phải node → hướng thoát sang phải).
  2. Sinh path dạng **Manhattan routing**: tối đa 1–3 đoạn gấp khúc (L-shape hoặc Z-shape), ưu tiên ít điểm gấp nhất.
  3. Tránh đè lên thân node khác (collision avoidance đơn giản — offset path ra ngoài bounding box của node chắn đư�?ng).
  4. Bo góc nhẹ (radius 4–8px) tại điểm gấp để không bị gãy cứng, nhưng v�? bản chất vẫn là đư�?ng thẳng vuông góc — không dùng cubic bezier.
- Khi node bị kéo di chuyển, path phải re-route lại real-time theo đúng thuật toán trên (không giữ path cũ).

---

## 2. Cổng kết nối chỉ hiện khi đã xác định mã hàng

**Hiện trạng:** cổng (IN/OUT, A/B, 1/P, 2/A, 3/R...) hiển thị ngay cả khi ô "mã hàng" đang trống → gây rối, vì lúc đó chưa biết thiết bị thật có bao nhiêu cổng, cổng ở đâu.

**Yêu cầu:**
- Node ở trạng thái **chưa có mã hàng hợp lệ**: ẩn toàn bộ các chấm tròn cổng, chỉ hiện khung node rỗng + ô nhập mã hàng (có thể để 1 placeholder m�? "chưa xác định cổng").
- Khi mã hàng được nhập và **match với catalog** (validate được model/part number thật):
  - Engine tra catalog lấy đúng số lượng cổng, tên cổng, vị trí chuẩn của đúng model đó.
  - Render cổng theo đúng dữ liệu catalog (không hard-code danh sách cổng cố định như hiện tại).
- Nếu mã hàng nhập sai/không tồn tại trong catalog: hiện border đ�? + tooltip lỗi, **không** render cổng giả định.

---

## 3. Bố trí cổng g�?n gàng, đúng theo chuẩn catalog

**Hiện trạng:** cổng nằm rải rác, không thẳng hàng, không theo logic chức năng (ví dụ ảnh 2: 1/P, 2/A, 4/B, 3/R, 5/S, 12/coil a, 14/coil b đang bị lệch hàng, khoảng cách không đ�?u).

**Yêu cầu bố trí chuẩn cho van điện từ (kiểu 5/2, 5/3 theo chuẩn ISO 5599-1 / SMC):**

| Vị trí trên node | Cổng | Ghi chú |
|---|---|---|
| Trên cùng, 2 cổng đối xứng | 2/A, 4/B | Cổng ra xy-lanh |
| Giữa | (thân van / tên model) | |
| Dưới, 3 cổng đối xứng | 3/R — 1/P — 5/S | P ở giữa, R/S hai bên |
| Dưới cùng, tách riêng 1 hàng | 12/coil a, 14/coil b | Cổng điện, không phải cổng khí — nên khác màu/icon |

**Nguyên tắc chung áp dụng cho m�?i node (xy-lanh, FRL, tiết lưu...):**
- Cổng cùng chức năng (khí vào/ra) canh **thẳng hàng ngang hoặc d�?c**, khoảng cách đ�?u nhau (spacing cố định, ví dụ 24–32px).
- Cổng IN luôn bên trái, OUT luôn bên phải (theo chi�?u dòng khí trong sơ đồ) — nhất quán toàn hệ thống.
- Cổng điện (coil) tách nhóm riêng, đặt dưới cùng, style khác (màu hồng/tím như đang có là hợp lý, giữ nguyên).
- Layout lấy từ **catalog datasheet thật** của hãng (SMC/Airtac/Festo...) — không tự đặt tùy ý.

---

## 4. Line phải xuất phát/kết thúc đúng tâm chấm tròn cổng

**Hiện trạng:** đư�?ng nối hiện lệch kh�?i tâm hình tròn biểu thị cổng (nhìn ảnh 1 thấy rõ line không chạm đúng vào circle).

**Yêu cầu:**
- �?iểm neo (anchor point) của mỗi connector **phải bằng chính toạ độ tâm (cx, cy)** của SVG `<circle>` đại diện cổng đó — lấy từ DOM/data thực tế của port, không hard-code offset tay.
- Khi port di chuyển do resize/re-layout node, connector phải tự cập nhật lại theo `getBoundingClientRect()` hoặc toạ độ port trong data model (không phải toạ độ tính tay lúc khởi tạo).
- Nên có 1 hàm chung `getPortAnchor(nodeId, portId)` trả v�? toạ độ tuyệt đối, m�?i nơi vẽ line đ�?u g�?i qua hàm này để tránh sai lệch giữa các chỗ.

---

## 5. Sau khi xuất BOM: đi�?n mã hàng ngược lại vào sơ đồ

**Yêu cầu:**
- Sau khi BOM được generate/finalize (tab "BOM" trong ảnh 3), với mỗi node trên sơ đồ:
  - Hiển thị **mã hàng đã ch�?n** (part number thật, ví dụ `SY3140-5LOU-C6`) ngay dưới tên node, thay vì chỉ để placeholder "mã hàng...".
  - Có thể thêm 1 dòng phụ nh�? hiển thị thông số then chốt đã tính (ví dụ: Cv, cỡ ống, áp suất làm việc) để ngư�?i đ�?c sơ đồ không cần mở lại bảng cấu hình.
- Mục tiêu: sơ đồ sau BOM trở thành **as-built diagram** — nhìn sơ đồ là biết ngay lắp thiết bị gì, mã gì, không cần tra chéo bảng BOM riêng.
- �?ồng bộ 2 chi�?u: nếu user sửa mã hàng trực tiếp trên BOM table, sơ đồ phải update theo, và ngược lại.

---

## 6. Engine tự phân tích/tính toán để ch�?n van, không h�?i ngược ngư�?i dùng

**Hiện trạng (ảnh 3):** form đang bắt user tự ch�?n "Loại van mặc định" (single/double) và tự ch�?n cỡ van (SY3000/5000/7000), kèm ghi chú "Engine chưa trích được Cv từ catalog" và "Engine không suy được" — tức là engine đang b�? cuộc và đẩy quyết định kỹ thuật cho user, đúng như bạn phản ánh.

**Yêu cầu — engine phải tự tính, chỉ h�?i user khi thực sự không đủ dữ liệu:**

1. **Ch�?n loại van (single/double solenoid) theo từng cơ cấu chấp hành:**
   - Nếu xy-lanh là single-acting (tác động đơn) → mặc định van 3/2.
   - Nếu xy-lanh là double-acting (tác động kép, như `CDM2L32-500Z` trong ảnh 1) → mặc định van 5/2.
   - Nếu ứng dụng cần giữ nguyên vị trí khi mất điện (home/hold) → gợi ý van 5/3 center-closed, kèm giải thích lý do — không bắt user tự biết khái niệm này.
   - �?ây là suy luận **theo từng cơ cấu riêng** (đúng như engine đang note "khai riêng từng cơ cấu"), nhưng phải **tự đ�? xuất mặc định + lý do**, chỉ để user override nếu muốn, không để trống bắt buộc ch�?n.

2. **Tính Cv/cỡ van (SY3000/5000/7000) từ dữ liệu đã có, không h�?i lại:**
   - Input đã có sẵn từ node xy-lanh: `bore_mm`, `rod_dia_mm`, hành trình (stroke), chu kỳ (s) — user đã nhập ở phần "�?i�?u kiện làm việc" (�?p suất 0.5 MPa, chu kỳ 1.5s, ống ø6...).
   - Công thức tính lưu lượng cần thiết:
     - Diện tích piston: `A = π/4 × bore²` (trừ diện tích cần piston ở hành trình lùi).
     - Vận tốc piston cần đạt: `v = stroke / (th�?i gian hành trình trong chu kỳ)`.
     - Lưu lượng khí thực tế (quy đổi theo áp suất làm việc, thư�?ng tính ở đi�?u kiện chuẩn ANR): `Q = A × v × (P_làm_việc + 1.013)/1.013`.
   - Quy đổi `Q` sang `Cv` (hoặc dùng trực tiếp bảng lưu lượng danh định của từng size van do hãng công bố, vì catalog thực tế cho theo dạng đồ thị lưu lượng — không phải Cv thuần).
   - So sánh với bảng lưu lượng danh định của SY3000 / SY5000 / SY7000 (lấy từ catalog thật, không suy diễn) → ch�?n size **nh�? nhất thoả đi�?u kiện** (có thể thêm hệ số an toàn ví dụ 1.2–1.5, tương ứng "Hệ số đồng th�?i" đang có sẵn trong form = 1.5).
   - Nếu nhi�?u cơ cấu dùng chung 1 van/manifold → cộng dồn lưu lượng các cơ cấu hoạt động đồng th�?i (theo đúng "Hệ số đồng th�?i" đã có trong form) trước khi ch�?n size.

3. **Chỉ h�?i user khi thật sự thiếu dữ liệu**, ví dụ:
   - Thiếu áp suất làm việc hoặc chu kỳ (bắt buộc phải có để tính lưu lượng).
   - Ứng dụng đặc biệt mà logic mặc định không suy được (ví dụ cần đi�?u khiển tốc độ khác nhau 2 chi�?u, cần xác nhận có dùng chức năng home không).
   - Khi h�?i, câu h�?i phải là dạng **xác nhận lựa ch�?n engine đã tính sẵn** ("Engine đ�? xuất van 5/2 cỡ SY5000 dựa trên lưu lượng X L/min — bạn có muốn thay đổi không?"), không phải để trống ép user tự tra catalog.

**Kết quả mong muốn:** form cấu hình chỉ còn h�?i các thông số vật lý đầu vào (áp suất, chu kỳ, bore...), còn "Loại van mặc định" và "Cỡ van" sẽ **hiển thị kết quả engine tự tính ra**, có nút để user override nếu cần, thay vì để trống bắt ch�?n như hiện tại.

---

## Tóm tắt ưu tiên implement

1. Fix anchor point line ↔ port (mục 4) — lỗi hiển thị rõ nhất, nên sửa trước.
2. �?ổi routing spline → orthogonal (mục 1).
3. Ẩn/hiện port theo mã hàng hợp lệ + lấy layout từ catalog (mục 2 + 3).
4. �?ồng bộ BOM → sơ đồ (mục 5).
5. Nâng cấp engine tính Cv/ch�?n van tự động (mục 6) — phần phức tạp nhất, cần dữ liệu catalog lưu lượng chuẩn của SY3000/5000/7000.
