# Model Selection Program của SMC — khảo sát 2026-08-26, bổ sung 2026-08-27

Yêu cầu (3) trong `PHân tích.txt`: *"vào trang này xem xét đánh giá xem có sử dụng
được không, trích xuất và phân tích dữ liệu, so sánh với catalog"* —
<https://www.smcworld.com/select/en-jp/>

## Kết luận ngắn

**Không trích xuất được, và lý do không phải kỹ thuật: từ cuối tháng 2/2026 SMC bắt
buộc đăng nhập tài khoản để dùng phần mềm chọn model.** Trang công khai chỉ còn
danh sách công cụ; toàn bộ phần tính toán nằm ở host riêng `mssc.smcworld.com` sau
cổng đăng nhập.

Nguyên văn trên trang từng công cụ:

> This service is for registered users only. Please log in to use it.
> NOTICE — Effective from the end of February 2026, user registration will be
> mandatory for using the selection software.

Tôi **không** tạo tài khoản và **không** đăng nhập thay bạn: việc đó cần thông tin
cá nhân của bạn và đồng ý điều khoản dịch vụ nhân danh bạn. Đó là quyết định của
bạn, không phải của tôi.

Thêm nữa, `mssc.smcworld.com` bị proxy của môi trường này chặn (403 tunnel), nên
ngay cả `robots.txt` của host đó cũng không đọc được — xem phần "Ba lỗi tuân thủ"
bên dưới, vì chính lần thử này làm lộ ra chúng.

## Đã tải những gì (5 request, ≤1 req/s, UA `PneuCompleteBot/0.1`)

| URL | kết quả |
|---|---|
| `/robots.txt` | 1.939 byte — phân tích ở dưới |
| `/select/en-jp/` | 166 KB · 30 công cụ · title "SMC- Model Selection Software" |
| `/select/fccs/en-jp/index.html` | 158 KB · **cổng đăng nhập** · app ở `mssc.smcworld.com/fccs/` |
| `/products/select_guide/en-jp/` | 152 KB · 0 bảng số liệu · cũng có cổng đăng nhập |
| `mssc.smcworld.com/robots.txt` | proxy chặn (403) |

## 30 công cụ — cái nào liên quan tới engine này

**12 công cụ tính toán (tên nằm ở lớp text, đọc được):**

| slug | tên trên trang | dùng để đối chiếu phần nào của engine |
|---|---|---|
| `fccs` | Flow Rate / Pressure / Pressure Drop / **Sonic Conductance** | ĐÁNG GIÁ NHẤT. `R-VLV-02` hiện ghi "catalog cho Cv dạng bảng nhưng engine chưa trích" nên phải hỏi `valve_series_size`. Dẫn nạp âm C là đúng thông số cần |
| `accs` | Air Consumption / Required Air Flow Capacity | đối chiếu `engine/calc.py` — lưu lượng tiêu thụ |
| `pdrfrcs` | Factory Main Piping Pressure Drop / Recommended Flow Rate | đối chiếu cỡ ống trục chính + `frl_drop` |
| `asccs` | Pressure / Temperature / Air Quantity / Status Change | trạng thái khí, ít liên quan |
| `cdtcs` | Charge and Discharge to/from Tank | chưa mô hình bình khí |
| `mipcgcs` | Moment of Inertia / Center of Gravity | chưa mô hình tải |
| `hccwacs` | Humidity / Condensed Water Amount | chọn bộ sấy — chưa mô hình |
| `lsccs` | Liquid / Steam / Gas flow | ngoài phạm vi khí nén |
| `cecs` | CO₂ Emissions / Compressor Power | ngoài phạm vi |
| `ucs` | Unit Conversion | không cần |
| `pcds` | **Pneumatic Circuit Diagram Creation Program** | trùng phần sơ đồ của yêu cầu (1)/(4) — nên xem để so cách họ mô hình mạch |
| `energy` | Air Pipeline Network | mạng phân phối khí — đúng chỗ engine đang bó tay (số lượng đầu nối) |

**18 công cụ chọn model (`*mss`): tên nằm TRONG ẢNH, `alt=""` rỗng nên không đọc
được từ lớp text.** Slug ghi lại để lần sau khỏi dò: `amss` `radmss` `afmss`
`acmss` `atmss` `brmss` `cdsss` `pccmss` `samss` `ramss` `agmss` `vatsmss` `dsmss`
`mvmss` `qeamss` `eamss` `tcmss` `abmss`. Tôi **không** suy tên từ chữ viết tắt —
đoán `acmss` = "Air Combination" nghe hợp lý nhưng đó vẫn là đoán, và tài liệu này
để dùng lại chứ không để phỏng đoán.

## Giá trị THẬT nếu bạn đăng nhập bằng tay

Không phải để lấy dữ liệu hàng loạt, mà để **kiểm chéo độc lập** những con số engine
đang dùng — đúng nguyên tắc "nguồn đối chiếu độc lập với catalog" đã dùng cho đồ thị
FRL (mã BOM khách hàng) và cho ngữ pháp (1.366 mã KQ2).

Ba phép kiểm cụ thể, mỗi phép chỉ cần vài số:

1. **`fccs`** → nhập cỡ van SY5000 + áp 0,5 MPa, lấy lưu lượng. So với ngưỡng engine
   đang dùng trong `R-VLV-02`. Nếu khớp thì bỏ được câu hỏi `valve_series_size`.
2. **`acmss`** (nếu đúng là chọn bộ AC) → nhập lưu lượng + áp nguồn, lấy cỡ AC. So
   với `engine/chart.pick_frl_size()` đọc từ `db/seed/charts/ac-flow.yaml`. Đây là
   phép kiểm mạnh nhất cho toàn bộ vòng số hoá đồ thị: 19 tiêu chí hiện chỉ chứng
   minh phép trích TỰ NHẤT QUÁN với nhãn trục, chưa chứng minh catalog in đúng.
3. **`accs`** → lưu lượng tiêu thụ của một xy-lanh ø40 hành trình 150, 30 ck/ph. So
   với `engine/calc.py`.

Nếu bạn chạy ba phép đó và đưa tôi con số, tôi thêm chúng vào ground truth và cổng
kiểm — không cần tôi vào trang.

**Đã dựng sẵn chỗ điền:** `db/seed/_doi-chieu-mss.yaml` có 10 ca, mỗi ca ghi rõ phần
`nhap:` (gõ đúng thế vào MSS) và số `engine:` đang cho, còn `mss:` để trống.
Điền xong chạy `python3 tools/doi_chieu_mss.py`.

Ô để trống = CHƯA KIỂM, không phải đạt: lệnh luôn in số ca chờ và trả mã 2 khi còn
ca chờ. `--doi-chung` nhồi số sai vào rồi đòi bắt hết — một phép so không thể báo
lệch thì không phải phép so.

## Sau khi bạn bỏ chặn mssc.smcworld.com (2026-08-27)

Host tới được rồi. Đã khảo sát kiến trúc — và kết luận KHÔNG đổi, vì rào cản không
nằm ở tầng mạng.

**Đo được:**

| thứ | kết quả |
|---|---|
| `mssc.smcworld.com/robots.txt` | HTTP 404 → không có luật riêng, cho phép (RFC 9309 §2.3.1) |
| `mssc.smcworld.com/fccs/` | HTTP 200 · 3.156 byte · vỏ Vue SPA, 21 tệp JS |
| dữ liệu sản phẩm trong JS tĩnh? | **KHÔNG.** Chunk lớn nhất 18 KB, 0 lần xuất hiện `SY3000/SY5000/SY7000`, `AC20/AC30`, `sonic`, `conductance`, `Cv` |
| nơi tính toán | **máy chủ**: `mssc.smcworld.com/fccs_server/index.php/api/` |

Bề mặt API đọc được từ `app.js` (dùng để hiểu kiến trúc, không phải để gọi):
`getAllLanguages` · `type_id_categories` · `select_options` · **`calculate`** ·
`login {userId, password}` · `updatePCConfig`. Gửi
`application/x-www-form-urlencoded`, `withCredentials: true`.

Vì dữ liệu KHÔNG có trong JS tĩnh, mọi con số chỉ ra từ `calculate` — tức từ bên
trong dịch vụ mà chủ trang ghi rõ *"This service is for registered users only."*

## Vì sao vẫn không tự đăng nhập / không tự gọi API

Không phải "không làm được". Là **không nên**, và đây là hai đường tôi từ chối:

1. **Gọi `calculate` mà không đăng nhập.** Bộ đăng nhập của app đặt một khoá ở
   sessionStorage tên `__fake_token__`, và interceptor của axios KHÔNG gắn header
   Authorization nào — dấu hiệu cho thấy cổng đăng nhập nằm ở phía client. Nhưng
   *ổ khoá lỏng không phải là lời mời*. Chủ trang đã nói rõ dịch vụ dành cho người
   đã đăng ký; gọi API vòng qua đó là dùng thứ mình không được phép dùng, dù máy
   chủ có kiểm hay không. Tôi KHÔNG thử `calculate`, và cũng không thử các endpoint
   khác để xem chỗ nào bỏ ngỏ.
   (Nhân đây: chỗ này bạn là khách hàng của SMC — nếu muốn, đây là điều đáng báo cho
   họ. Tôi chỉ nêu sự kiện, không viết công cụ khai thác.)
2. **Đăng nhập bằng tài khoản của bạn.** Mật khẩu vào phiên này là vào cả lịch sử
   shell và log. Và trích tự động từ sau cổng đăng nhập là chuyện ĐIỀU KHOẢN DỊCH
   VỤ — khác hẳn đọc trang công khai, tôi chưa đọc điều khoản đó, và nó không phải
   việc tôi quyết thay bạn.

**Hai đường sạch:**
- Bạn mở trình duyệt, đăng nhập, đọc 10 số, điền vào `db/seed/_doi-chieu-mss.yaml`.
  Tôi đã dựng sẵn phép so + đối chứng âm nên phần việc của bạn chỉ là đọc số.
- Muốn tự động thì xin phép SMC (API hoặc thoả thuận dùng dữ liệu). Đó là đường
  đúng, và nó cũng mở ra nhiều hơn 10 con số.

## Ba lỗi tuân thủ robots.txt phát hiện nhờ lần thử này

Đây là phần **có sửa được ngay**, và là kết quả dùng được nhất của yêu cầu (3).

`robots.txt` của smcworld.com có hai khối `User-agent: *`:

```
User-agent: *                       ← khối Cloudflare chèn
Content-Signal: search=yes,ai-train=no,use=reference
Allow: /
... (các khối chặn ClaudeBot, GPTBot, CCBot, Amazonbot…)
User-agent: *                       ← khối của chính SMC
Disallow: /products/*/global.do
Disallow: /products/*/ps.do
Disallow: /support/req/*
```

1. **`urllib.robotparser` BỎ khối `*` thứ hai.** CPython `_add_entry()` ghi rõ
   *"the first default entry wins"*. Ba dòng `Disallow` của chính SMC bị bỏ hẳn.
2. **Stdlib url-encode dấu `*` trong đường dẫn** → `/products/%2A/global.do`, nên
   mọi luật có `*` vô hiệu một cách im lặng.
3. **`robots_ok()` coi MỌI lỗi là "mặc định cho phép".** Proxy trả 403 cho
   `mssc.smcworld.com` mà hàm vẫn nói CHO PHÉP — crawler sẵn sàng tải một host nó
   chưa từng đọc được luật.

Hậu quả nếu không sửa: crawler tưởng được phép tải ba đường dẫn chủ site đã chặn.
**Đã kiểm DB: 0/2718 URL đã tải thuộc các đường đó**, nên chưa từng vi phạm — nhưng
đó là may, không phải do luật đang chạy đúng.

Sửa: `crawler/robots.py` (bộ đọc riêng, stdlib-only) + `tests/test_robots.py`
(32 kiểm, fixture là robots.txt thật nên chạy offline). Test còn khẳng định stdlib
SAI ở đúng hai chỗ đó — ngày nào stdlib sửa thì test đỏ và bỏ được bộ đọc riêng.
Lỗi 3 sửa theo RFC 9309 §2.3.1: 4xx = không có tệp → cho phép; 5xx hoặc lỗi
mạng/proxy → chặn hết.

## Ràng buộc còn nguyên

- `Content-Signal: ai-train=no, use=reference` — thiết kế theo luật của dự án này
  không huấn luyện mô hình, nên `ai-train=no` được tôn trọng; đọc để tham chiếu là
  đúng `use=reference`.
- **robots.txt chặn `ClaudeBot`, `GPTBot`, `CCBot`, `Amazonbot`, `Applebot-Extended`,
  `Bytespider`, `Google-Extended`, `meta-externalagent` toàn site.** Crawler của dự
  án khai đúng danh tính riêng (`PneuCompleteBot/0.1`) nên rơi vào nhóm `*`; tuyệt
  đối KHÔNG giả dạng trình duyệt và KHÔNG mượn tên bot khác. `tests/test_robots.py`
  có kiểm đúng điều này.
- `Allow: /` **không phải giấy phép bản quyền**. Nội dung tải về dùng nội bộ, không
  phát hành lại, trừ khi có phép của SMC.
- ≤ 1 request/giây, mỗi host một luồng — `crawler/fetcher.py` đã ép.
