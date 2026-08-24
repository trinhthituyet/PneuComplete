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

Phần mềm làm việc trên **cây dự án**: bạn khai thiết bị theo quan hệ *cái gì gắn
vào cái gì*, đúng như thực tế lắp máy.

### Chỉ cần nhập MÃ XY-LANH

Bấm **+ Trạm** ở cột trái. Phần mềm tạo sẵn một trạm gồm **1 van + 1 xy-lanh**,
cả hai để trống mã. Bạn chỉ gõ **mã xy-lanh**:

```
CDM2L32-500Z
```

Từ một mã đó phần mềm tự ra: 2 tiết lưu (đúng cỡ ren cửa xy-lanh) · 2 cảm biến ·
1 van (đúng cỡ theo lưu lượng) · floating joint · ống · bộ xử lý khí.

> **Để trống mã van là có chủ đích.** Phần mềm tính cỡ van từ lưu lượng khí của
> các xy-lanh bạn nhập. Muốn tự chọn thì gõ mã vào, phần mềm sẽ không ghi đè.

### Cây phân cấp — cái gì là con của cái gì

```
Bộ xử lý khí (nguồn chung)
└── Manifold                     1 cái cho cả máy
    ├── Trạm SV1                 ← van
    │   └── Xy-lanh              ← BẠN NHẬP MÃ Ở ĐÂY
    │       ├── Tiết lưu cửa A   ← vặn vào cửa xy-lanh
    │       └── Tiết lưu cửa B
    └── Trạm SV2 → ...
```

Ba quan hệ này lấy từ catalog, không phải quy ước:

- **Tiết lưu là con của xy-lanh** — nó vặn trực tiếp vào cửa xy-lanh (ren ngoài
  R1/8 vào cửa trong Rc1/8), nên cỡ ren suy ra được, bạn không phải nhập.
- **Một manifold cho cả máy** — BOM máy thật: 11 van dùng **1** đế `SS5Y5-20-12`
  12 station, không phải 11 đế rời.
- **Giảm âm gắn ở manifold** — xả là chung, BOM thật chỉ có 2 cái cho 11 van.

Nếu bạn đặt sai chỗ, phần mềm **tự dịch về đúng cha và nói rõ đã dịch gì** — xem
dòng chữ cạnh tên phần mềm sau khi bấm Dựng BOM.

### Thêm thiết bị

Bấm một node → khung **Thiết bị con** → chọn loại → **+ Thêm**. Danh sách chỉ
hiện loại **lắp được vào đó**, nên không thể tạo cây sai.

### Ba màu trạng thái

| Màu | Nghĩa |
|---|---|
| 🟢 xanh | Đã chốt mã — sẵn sàng lên BOM |
| 🟡 vàng | Mới biết loại (đã ghi thuộc tính, chưa có mã) |
| 🔴 đỏ | Trống |

Vòng tròn trên đầu là tỉ lệ đã chốt mã.

### Bốn tab

| Tab | Nội dung |
|---|---|
| **Cây dự án** | khai thiết bị |
| **Cấu hình** | **Engine tự tính** (cỡ van, loại van — hiện kết quả, có ô ghi đè) và **Cần bạn khai** (những gì không suy được, kèm lý do) |
| **BOM** | kết quả theo **cây thụt lề** — phụ kiện nằm dưới thiết bị mẹ, đúng như bạn khai |
| **Sơ đồ** | vẽ lại cây kèm mã đã chọn — nhìn là biết lắp gì |

Bấm **CSV** để mở bằng Excel.

### Khi phần mềm cần bạn quyết

Mỗi mục chỉ 3 dòng ngắn:

```
R-FRL-01  ⚠ thiếu Cỡ cửa đường trục chính
Sai ở:    → main_line_port_size
Cần sửa:  → Chọn Cỡ cửa đường trục chính
Chọn:     [1/8] [1/4] [3/8] [1/2]      ← bấm là điền thẳng vào Cấu hình
▸ Chi tiết / Debug                      ← lý do dài, số trang catalog
```

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

