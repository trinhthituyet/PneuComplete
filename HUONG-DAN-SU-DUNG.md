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

### Bước 1 — Nhập xy-lanh

Ở bảng **Actuator**, gõ mã xy-lanh vào cột "Mã hàng", ví dụ:

```
CDM2L32-500Z
MGPM25-200Z-M9BL
CDQSB20-25D-M9BZ
```

Gõ xong bấm ra ngoài ô, phần mềm kiểm tra ngay:

- **Viền xanh** → hiểu được mã, hiện luôn thông số (đường kính, hành trình…)
- **Viền đỏ** → có chỗ chưa hiểu, hiện rõ *"chưa hiểu phần …"*

Nhập số lượng, và chọn **Loại van** cho từng xy-lanh:

| Chọn | Khi nào |
|---|---|
| `single` | Cơ cấu kẹp, đẩy một chiều |
| `double` | Đi–về, cần giữ vị trí khi mất điện |
| `3pos_closed` | Cần dừng được ở giữa hành trình |
| `3pos_exhaust` | Dừng giữa, xả khí hai buồng |
| `3pos_pressure` | Dừng giữa, giữ áp hai buồng |

### Bước 2 — Khai những thứ phần mềm không tự biết

Mục **"Cần bạn khai"** liệt kê các thông tin phần mềm **không thể tự suy ra**,
mỗi dòng kèm lý do vì sao. Ví dụ tổng mét ống phụ thuộc layout máy của bạn —
phần mềm không biết khoảng cách từ tủ van tới từng xy-lanh.

**Để trống cũng được.** Phần mềm sẽ không tự đoán, mà báo ở mục
*"Cần bạn quyết định"* để bạn tự điền sau.

### Bước 3 — Bấm "Dựng BOM"

Kết quả bên phải gồm:

- **Tính toán** — lực đẩy/kéo, khí tiêu thụ, tốc độ piston, kèm các giả định
- **BOM** theo 6 tầng: actuator · van · xử lý khí · đường ống · phụ kiện · điện
- **Cảnh báo** — chỗ cần chú ý về kỹ thuật
- **Cần bạn quyết định** — chỗ phần mềm **không đoán**

Bấm **Xuất CSV** để mở bằng Excel.

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

Phần mềm đang đúng khoảng **60% số dòng** khi so với BOM máy thật (máy 23-432).
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
| Nhập mã mà viền đỏ | Phần mềm chưa biết họ sản phẩm đó — xem mục dưới |

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

