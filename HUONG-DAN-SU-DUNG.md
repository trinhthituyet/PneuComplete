# PneuComplete — Hướng dẫn sử dụng

Phần mềm dựng danh sách vật tư (BOM) khí nén: bạn nhập xy-lanh, phần mềm đề xuất
van, ống, phụ kiện, cảm biến còn lại — kèm **lý do** cho từng dòng.

---

## 1. Mở phần mềm

Phần mềm chạy trong **Docker**. Cần cài **Docker Desktop** một lần duy nhất, sau
đó không phải cài Python hay bất cứ thư viện nào.

### Lần đầu — cài Docker Desktop

1. Vào <https://www.docker.com/products/docker-desktop>
2. Tải bản cho máy bạn
   - **macOS:** chú ý chọn đúng **Apple Silicon** hay **Intel**.
     Không biết máy loại nào:  → *About This Mac*. Thấy chữ "Apple M1/M2/M3…"
     là Apple Silicon.
   - **Windows:** tải bản Windows, cài, khởi động lại máy nếu Docker yêu cầu.
3. Mở Docker Desktop, chờ tới khi:
   - macOS: hình **con cá voi** trên thanh menu **đứng yên**, không nhấp nháy
   - Windows: Docker Desktop báo **"Engine running"**

### Mở phần mềm

| Máy | Nháy đúp tệp |
|---|---|
| **macOS** | **`PneuComplete-Docker.command`** |
| **Windows** | **`PneuComplete-Docker.bat`** |

> **Lần đầu chạy sẽ lâu: 5–15 phút.** Docker phải tải và dựng phần mềm, cần
> khoảng **1 GB** ổ đĩa trống và có mạng internet. Cửa sổ đen chạy rất nhiều
> dòng chữ — **bình thường, cứ để nó chạy**.
>
> **Từ lần thứ hai chỉ mất vài giây.**

Xong, trình duyệt tự mở trang phần mềm.

### Tắt phần mềm

Bản Docker chạy **ngầm** — đóng cửa sổ đen **không** tắt nó. Ưu điểm: đóng nhầm
cửa sổ cũng không mất việc đang làm.

Muốn tắt hẳn, nháy đúp:

| Máy | Tệp |
|---|---|
| **macOS** | **`Tat-PneuComplete.command`** |
| **Windows** | **`Tat-PneuComplete.bat`** |

Tắt **không** làm mất phương án BOM đã dựng.

### Lần đầu trên macOS báo "không thể mở"

macOS chặn tệp tải từ mạng. Cách mở:

1. **Nháy phải** vào `PneuComplete-Docker.command`
2. Chọn **Open**
3. Hộp thoại hiện ra → bấm **Open** lần nữa

Chỉ cần làm một lần.

### Máy không cài được Docker

Một số máy công ty không cho cài Docker. Khi đó dùng cách chạy trực tiếp:

1. Cài **Python 3.10 trở lên** từ <https://python.org> → Downloads
   *(Windows: nhớ **tích ô "Add Python to PATH"** ở màn hình đầu tiên)*
2. Mở cửa sổ dòng lệnh, gõ: `pip3 install pyyaml`
3. Nháy đúp **`PneuComplete.command`** (macOS) hoặc **`PneuComplete.bat`** (Windows)

Cách này cửa sổ đen **phải để nguyên, đừng đóng** — đóng là phần mềm ngừng chạy.

> Vì sao cần `pip3 install pyyaml`: phần mềm đọc các tệp quy tắc kỹ thuật viết
> bằng định dạng YAML, mà Python không đọc được sẵn định dạng đó. Bản Docker đã
> có thư viện này nên không phải làm gì.

---

## 2. Dùng phần mềm

Phần mềm làm việc trên **sơ đồ đấu nối**: bạn vẽ các thiết bị thành khối và nối
dây giữa chúng, thay vì chỉ liệt kê danh sách.

### Bước 1 — Đưa thiết bị vào sơ đồ

Cột trái là danh sách **nhóm thiết bị** (Xy-lanh, Van điều khiển, Bộ xử lý khí,
PLC, Tuỳ chỉnh…). Có hai cách:

- **Kéo** một nhóm từ cột trái vào vùng giữa, hoặc **bấm** vào nhóm đó
- **Nhập nhanh nhiều xy-lanh:** dán danh sách mã vào ô "Nhập nhanh", mỗi dòng
  một mã, rồi bấm *Tạo node xy-lanh*. Viết `MGPM25-200Z-M9BL x4` để đặt số lượng.

Khối mới hiện ra **rỗng**, có tiêu đề là tên nhóm và **màu riêng theo loại**
(xy-lanh xanh, van tím, xử lý khí xanh lá, ống cam, phụ kiện vàng, điện hồng).

### Bước 2 — Gõ mã hàng vào khối

Gõ vào ô trong khối rồi bấm ra ngoài. Phần mềm kiểm ngay:

- **Viền xanh + dấu ✓** → hiểu được mã, hiện luôn thông số (đường kính, hành trình)
- **Viền đỏ + dấu ✗** → ghi rõ *"chưa hiểu phần …"*
- **Viền xám nét đứt** → bạn đã bật *mã tự do*, phần mềm không kiểm

Khi mã đúng, phần mềm còn **tự thay các cổng của khối** bằng cổng thật đọc từ
catalog — ví dụ xy-lanh hiện đúng 2 cửa khí `A (Rc1/8)` và `B (Rc1/8)`.

### Bước 3 — Nối dây

Cổng là các **điểm tròn** quanh khối: cửa khí ở hai bên, cửa điện ở đáy.

1. Bấm vào một cổng → vào chế độ nối, dây bám theo con trỏ
2. Bấm cổng đích → xong

Giữa hai lần bấm bạn vẫn **di chuyển và phóng to** được để nhắm đúng cổng. Nếu
quen tay kéo-thả thì kéo từ cổng nguồn sang cổng đích cũng được. **Esc** để huỷ.

Phần mềm tự đoán loại kết nối theo cặp thiết bị (van → xy-lanh là *điều khiển*,
bộ xử lý khí → van là *nguồn cấp*). Không đoán được thì nó **hỏi** chứ không tự
chọn bừa. Bấm vào dây để đổi loại.

> **Vì sao phải nối dây:** nhờ đó phần mềm biết 8 cụm van dùng **chung một** bộ
> xử lý khí, biết van nào điều khiển xy-lanh nào, và lấy được điện áp coil từ
> khối PLC. Danh sách phẳng không diễn đạt được những quan hệ này.

### Bước 4 — Khai thêm ở cột phải

Bấm một khối → thẻ **Node** hiện chi tiết: nhãn, mã hàng, số lượng, loại van, và
công tắc **"Mã tự do"** cho thiết bị ngoài catalog SMC.

Thẻ **Cấu hình** chứa mục *"Cần bạn khai"* — những thông tin phần mềm **không thể
tự suy**, mỗi dòng kèm lý do. Để trống cũng được, phần mềm sẽ báo ở *"Cần bạn
quyết định"* thay vì đoán.

### Bước 5 — Bấm "Dựng BOM"

Phần mềm **tự quyết** những gì nó tính được, không hỏi bạn nữa:

- **Cỡ van** — tính từ lưu lượng khí của các xy-lanh bạn nhập
- **Loại van** — tác động kép → van 5/2, tác động đơn → van 3/2

> **Nhưng loại van thì hãy kiểm lại.** Máy thật thường dùng lẫn nhiều loại: cơ cấu
> kẹp dùng 5/2 một cuộn, cơ cấu cần dừng giữa hành trình dùng 5/3. Phần mềm không
> biết chức năng từng cơ cấu nên nó đoán là 5/2 hai cuộn và **hiện độ tin cậy 50%**
> trên dòng đó. Sửa ở từng khối để lên 90%.


Thẻ **BOM** hiện:

- **Đọc được từ sơ đồ** — mấy vùng khí, xy-lanh nào đã có van, điện áp lấy từ PLC
- **Tính toán** — lực đẩy/kéo, khí tiêu thụ
- **BOM** theo 6 tầng, dòng nhập tay có nhãn *"nhập tay"*
- **Engine đã tự quyết** — những gì phần mềm tự tính, để bạn kiểm lại
- **Cảnh báo** và **Cần bạn quyết định** — mỗi mục chỉ 3 dòng ngắn:
  *sai ở đâu · cần sửa gì · bấm chọn giá trị*. Muốn xem lý do dài, số trang
  catalog thì mở **Chi tiết / Debug**.

Bấm **CSV** để mở bằng Excel.

### Thanh công cụ

| Nút | Việc |
|---|---|
| ↶ ↷ | Hoàn tác / làm lại (`Ctrl+Z`, `Ctrl+Shift+Z`) |
| Nhân bản | Copy khối đang chọn — tiện khi có nhiều cụm giống nhau |
| Xoá | Xoá khối hoặc dây đang chọn (`Delete`) |
| Vừa khung | Thu cả sơ đồ vào vừa màn hình |
| Mã tự do | Bật/tắt nhanh cho khối đang chọn |

Lăn chuột để phóng to/nhỏ, kéo vùng trống để di chuyển sơ đồ.

---

## 3. Ba điều cần hiểu để dùng đúng

### Phần mềm không đoán bừa

Chỗ nào không đủ dữ liệu để chắc chắn, nó **báo ra** thay vì điền một mã trông
có vẻ đúng. Thà thiếu vài dòng hơn đặt sai hàng.

### Mỗi dòng đều có lý do — hãy đọc

Dưới mỗi mã hàng có dòng chữ nhỏ ghi mã quy tắc và lý do, ví dụ:

> `R-SPD-01:` Xy-lanh tác động 2 chiều cần tiết lưu khí xả ở cả hai cửa…

Có dòng ghi thêm **nguồn tra cứu** (số trang catalog) hoặc **độ tin cậy**
dưới 100%. Độ tin cậy thấp nghĩa là bạn nên kiểm lại dòng đó.

### Đây là bản đề xuất, không phải bản chốt

Phần mềm đang đúng khoảng **18% số dòng** khi so với BOM hai máy thật.

> Con số này **tụt từ 36%** không phải vì phần mềm tệ hơn, mà vì trước đây các
> dòng van bị **loại khỏi phép đo** (phần mềm từ chối đoán nên không có gì để so).
> Nay phần mềm tự đề xuất van, nên van được đưa vào đo — và nó đang sai nhiều ở
> **số lượng từng loại van**. Đó là chỗ cần bạn sửa nhất.
Nó giúp bạn **không bỏ sót** và **không phải tra catalog**, nhưng **người ký BOM
vẫn là bạn**. Luôn xem qua toàn bộ, đặc biệt các dòng có cảnh báo hoặc độ tin
cậy thấp.

---

## 4. Gặp sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| "Máy chưa có Docker Desktop" | Cài theo mục 1 ở trên |
| "Docker Desktop chưa khởi động xong" | Mở Docker Desktop, chờ con cá voi đứng yên (Windows: "Engine running"), rồi mở lại phần mềm |
| "Không dựng được phần mềm" | Kiểm tra mạng internet và ổ đĩa còn ≥1 GB trống. Máy công ty có thể chặn Docker Hub — nhờ IT |
| Cửa sổ đen hiện lỗi rồi tắt | Chụp ảnh cửa sổ, gửi người phụ trách |
| Trình duyệt không tự mở | Sao chép địa chỉ `http://localhost:8765` vào trình duyệt |
| Trang trắng / không tải | Nháy đúp `Tat-PneuComplete`, rồi mở lại phần mềm |
| Mở lại thấy mất phương án cũ | Kiểm tra thư mục `data/` còn nằm cạnh các tệp kia không |
| "Hệ thống không cho phép mở kết nối" | Tường lửa hoặc diệt virus đang chặn — nhờ IT cho phép Python kết nối nội bộ |
| "Thiếu tệp dữ liệu" | Giải nén lại **toàn bộ** thư mục, đừng chỉ lấy vài tệp |
| Nhập mã mà viền đỏ | Phần mềm chưa biết họ sản phẩm đó — bật **Mã tự do** để vẫn đưa vào BOM, xem mục dưới |
| Nối dây mà bị cảnh báo sai cổng | Bạn đang nối cổng điện vào cổng khí. Phần mềm không chặn nhưng dòng BOM từ dây đó không đáng tin |
| Đổi mã rồi mất dây nối | Mã mới có cổng khác — dây nối vào cổng không còn tồn tại bị bỏ, có thông báo ở góc phải |

### Phần mềm chưa biết mã của tôi

Hiện phần mềm đọc được **16 họ sản phẩm** SMC — chính là con số cửa sổ đen in ra
lúc khởi động. Nếu bạn nhập mã thuộc họ khác,
nó sẽ báo không hiểu. Muốn thêm họ mới thì cần **trang How-to-Order** của họ đó
(bản PDF hoặc ảnh) — gửi cho người phụ trách phần mềm.

---

## 5. Dữ liệu của bạn nằm ở đâu

Mọi thứ chạy **trên máy bạn**, không gửi ra internet. Chỉ máy này mở được trang
phần mềm — máy khác trong mạng công ty không vào được.

Các phương án BOM đã dựng nằm ở:

| Cách chạy | Tệp dữ liệu |
|---|---|
| Docker | `data/pneu.db` (thư mục `data/` cạnh các tệp phần mềm) |
| Chạy trực tiếp | `pneu.db` cùng thư mục |

**Sao lưu tệp đó là sao lưu toàn bộ công việc của bạn.** Cứ chép ra USB hoặc ổ
mạng theo định kỳ.

> Dữ liệu để **ngoài** phần mềm là có chủ đích: khi bạn nhận bản cập nhật mới,
> chỉ phần mềm được thay, còn phương án BOM của bạn giữ nguyên.

### Phần mềm chỉ giữ 200 phương án gần nhất

Mỗi lần bấm **Dựng BOM** là một phương án được lưu. Phần mềm giữ **200 lần gần
nhất**, cũ hơn thì tự xoá — nếu không, tệp dữ liệu phình lên mãi.

200 lần là rất nhiều cho việc dùng hàng ngày. Nhưng **phương án nào cần giữ lâu
thì hãy bấm "Xuất CSV" và lưu tệp đó lại** — tệp CSV là của bạn, không bị xoá.

