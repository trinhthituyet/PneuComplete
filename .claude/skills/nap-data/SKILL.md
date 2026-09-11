---
name: nap-data
description: Nạp dữ liệu mới vào PneuComplete — đồ thị catalog, ngữ pháp mã hàng, ràng buộc requires, phân loại thiết bị, luật, BOM khách hàng. Dùng khi thêm/sửa bất cứ thứ gì trong db/seed/, khi chạy cổng kiểm dữ liệu, hoặc khi làm mới db/seed/pneu-seed.db. Cũng dùng khi cần tải trang web nhà sản xuất.
---

# Nạp dữ liệu cho PneuComplete

Dự án này sai một dòng thì người ta **đặt hàng sai**. Nên mọi đường nạp dữ liệu đều
đi qua cổng, và cổng nào cũng phải chứng minh được là nó BẮT ĐƯỢC lỗi.

## Sáu luật, mỗi luật đã đổi bằng một con bug

1. **Cổng trước dữ liệu.** Không ghi YAML rồi kiểm sau. Bộ sinh phải TỰ gọi cổng và
   từ chối ghi khi chưa đạt — `parsers/chart_yaml.py:build()` gọi
   `tests/test_chart.py` rồi `raise` nếu != 0. Làm cho việc ghi KHÔNG THỂ xảy ra khi
   kiểm chưa đạt, thay vì nhắc nhau nhớ chạy kiểm.
2. **Cổng không bao giờ FAIL được thì không phải cổng.** Mỗi bộ cổng phải có ĐỐI
   CHỨNG ÂM: cố ý làm sai rồi đòi bắt được. `tests/test_chart.py` gieo 13 lỗi;
   `tools/doi_chieu_mss.py --doi-chung` nhồi số sai. Đã hai lần một tiêu chí mất
   hết sức mạnh mà vẫn báo PASS (C6 chặn trần đúng bằng dung sai; C16 điểm dò rơi
   vào chỗ mọi cỡ bằng nhau).
3. **Nguồn đối chiếu phải ĐỘC LẬP với nguồn trích.** Ba nguồn đang dùng: lớp text
   của PDF (độc lập với việc dò đường cong) · mã BOM khách hàng thật (độc lập với
   catalog) · bất biến vật lý (áp đặt ≤ áp vào; sụt áp = 0 ở lưu lượng 0; thân lớn
   giữ áp tốt hơn). Đọc lại chính thứ mình vừa trích rồi thấy khớp thì không chứng
   minh gì.
4. **Gap thay vì đoán.** Không suy được thì `status='gap'`, không bịa mã trông hợp
   lý. Và **thiếu dữ liệu KHÔNG được làm vật tư biến mất**: gap khai `layer` +
   `item_vn` + `node_type` để nó thành một dòng BOM và một node sơ đồ, mã để trống.
5. **Ô trống ≠ đạt.** Chỗ chờ người điền phải trả mã khác 0 và in số ca CHỜ. Để
   trống hết mà báo "0 lệch · ĐẠT" là chỗ cổng mục ruỗng.
6. **Kết luận âm cũng là dữ liệu.** "Đã tra, không rút được ràng buộc, vì …" phải
   ghi lại (`NO_MATRIX` trong `grammar_requires.py`, phần cuối `pdf_code_list.py`,
   đuôi `jb.yaml`). Không ghi thì lần sau dò lại từ đầu, hoặc tưởng là bỏ sót.

**Chạy thật mọi lệnh trước khi viết nó vào tài liệu.** Xem bẫy đầu tiên ở phần
"Bẫy đã mắc" — một lệnh xem trước đã chết lặng lẽ vì không có cổng nào chạy nó.

**Đo trước khi viết.** Mỗi lần bỏ qua bước này là một vòng lặp không hội tụ. Ba lần
liên tiếp việc suy ô đồ thị từ CỤM ĐƯỜNG CONG bị phá vì đổi bộ lọc đường cong; chỉ
đảo lại phụ thuộc (suy ô từ NHÃN TRỤC) mới xong.

## Sáu đường nạp

| dữ liệu | tệp đích | công cụ | cổng |
|---|---|---|---|
| đồ thị catalog (lưu lượng, sụt áp, độ ổn định áp) | `db/seed/charts/*.yaml` | `parsers/chart_yaml.py` | `tests/test_chart.py` — 19 tiêu chí + 13 đối chứng âm |
| ngữ pháp mã hàng | `db/seed/grammar/*.yaml` | `crawler/grammar_seed.py` | `tests/test_parser.py` + parse ngược mã BOM thật |
| ràng buộc `requires` (tổ hợp có thật) | chèn vào `db/seed/grammar/*.yaml` | `parsers/grammar_requires.py` (bảng ✕) · `parsers/pdf_code_list.py` (danh sách mã) | G1–G4 trong chính công cụ |
| phân loại mã → loại thiết bị | `engine/classify.py` | sửa tay `SERIES_NODE_TYPE` | `G-CLASS-01/02` trong `tests/test_graph.py` |
| luật sinh BOM | `db/seed/rules.yaml` | `bom.seed_rules()` tự nạp | `tests/test_bom.py` + `ingest/golden.py` |
| BOM khách hàng (để đối chiếu) | bảng `machine`, `bom_line` | `ingest/bom_import.py` | `ingest/golden.py` |

## Trình tự chuẩn cho mỗi đường

Luôn ba nhịp: **xem trước → cổng → mới ghi**. Không có công cụ nào ghi ngay.

```sh
# 1. ĐỒ THỊ
python3 -m parsers.pdf_chart DOCUMENT/FRL/es40-69-AC-D.pdf 22   # xem trích được gì
python3 tests/test_chart.py                                     # cổng + đối chứng âm
python3 -m parsers.chart_yaml                                   # xem SẼ ghi gì
python3 -m parsers.chart_yaml --write                           # ghi (tự gọi lại cổng)

# 2. NGỮ PHÁP  (viết tay YAML, không máy trích — xem "Ngữ pháp" bên dưới)
python3 -m crawler.grammar_seed jb.yaml     # nạp 1 tệp
python3 -m crawler.grammar_seed             # nạp tất cả
python3 tests/test_parser.py

# 3. RÀNG BUỘC requires
python3 -m parsers.pdf_option_matrix DOCUMENT/FRL/es40-69-AC-D.pdf 20   # xem bảng ✕
python3 -m parsers.grammar_requires          # xem + chạy G1–G4
python3 -m parsers.grammar_requires --write  # chỉ ghi khi cả 4 cổng PASS
python3 -m parsers.pdf_code_list --write     # họ liệt kê thẳng mã (KQ2, AS)
python3 -m crawler.grammar_seed              # nạp lại vào DB

# 4. BOM KHÁCH HÀNG
python3 -m ingest.bom_import BOM/*.xlsx
python3 -m ingest.bom_import --report
python3 -m ingest.golden                     # KHÔNG được tụt so với lần trước
```

Sau mọi thay đổi dữ liệu, làm mới DB đóng gói — nếu không thì bản Docker chạy DB cũ
và test_docker sẽ bắt:

```sh
python3 tools/package.py --clean-db && cp dist/pneu.db db/seed/pneu-seed.db
```

## Cổng phải xanh trước khi commit

```sh
python3 tests/test_parser.py    # parse mã hàng
python3 tests/test_bom.py       # luật + dựng BOM
python3 tests/test_web.py       # API
python3 tests/test_graph.py     # sơ đồ, phân loại theo mã, liên kết chéo
python3 tests/test_chart.py     # 19 tiêu chí đồ thị + đối chứng âm
python3 tests/test_robots.py    # tuân thủ robots.txt (chạy offline)
node    tests/test_ui.js        # hình học sơ đồ + hợp đồng UI↔API
python3 tests/test_docker.py    # đóng gói
python3 -m ingest.golden        # điểm golden
```

`python3 tools/package.py` chạy sẵn 6 trong số đó và chặn đóng gói nếu đỏ.

**Golden chỉ được đi lên.** Con số hiện tại nằm ở dòng `TỔNG:` — nếu tụt thì thay
đổi vừa rồi làm hỏng thứ đang đúng, dù mọi test khác xanh. Vật tư chưa có mã KHÔNG
được tính là đúng.

## Ngữ pháp mã hàng: viết tay, và vì sao

Máy trích sơ đồ How-to-Order cho ra rác ở nhiều họ (`AMC-E` trong DB là bản máy
trích lỗi: hai ô cùng tên `numeric`, và một ô `stroke` cho bộ xả khí — thứ không có
hành trình). Nên ngữ pháp mới là **đọc PDF bằng mắt rồi viết YAML**, kèm:

- `source:` — tên PDF + số trang + tên bảng. Không có nguồn thì không nạp.
- **hai đường đọc độc lập** khi có thể. Ví dụ `jb.yaml`: ren suy từ MÃ
  (`JB20-5-080` → M5×0,80) và đối chiếu với cột ren IN TRONG BẢNG — khớp 10/10.
- `attrs` phải là thứ luật cần khớp (`rod_end_thread`, `bore_mm`, `port_size`…),
  không phải mọi thứ in trên trang.
- Sau khi nạp: parse ngược **mã BOM khách hàng thật** của họ đó. Ràng buộc nào loại
  một mã CÓ THẬT là ràng buộc sai.

Thêm ngữ pháp mới thì phải thêm một dòng vào `engine/classify.py`
`SERIES_NODE_TYPE`, nếu không cổng `G-CLASS-01` đỏ — chủ ý: người dùng gõ mã hợp lệ
mà phần mềm nói "không biết đây là gì" là lỗi.

## Bẫy đã mắc — đọc trước khi sửa mã trích

- **Cổng đồ thị BỎ QUA khi không có `DOCUMENT/`** và trả về 0, tức XANH mà không
  kiểm gì. Trước khi tin "19/19 PASS", phải thấy nó in đủ tên tiêu chí; nếu thấy
  dòng `BỎ QUA: không có DOCUMENT/` thì cổng chưa chạy.
- **Lệnh xem trước có thể mục ruỗng mà không ai biết.** Chính khi viết skill này đã
  phát hiện `python3 -m parsers.pdf_chart <pdf> <trang>` chết bằng
  `KeyError: 'n_paths'`: `main()` còn in các khoá của thời `digitize()` coi mỗi
  trang là MỘT đồ thị, còn cổng và bộ sinh thì gọi `digitize()` trực tiếp nên không
  ai chạm vào `main()`. Nhịp "đo trước khi ghi" âm thầm không dùng được — và cách
  duy nhất phát hiện là CHẠY THẬT từng lệnh mình định viết vào tài liệu. Giờ
  `tests/test_chart.py` kiểm luôn lệnh đó (cả trang lưu lượng và trang áp→áp), nên
  nó không rot lại được.
- **Ô đồ thị suy từ NHÃN TRỤC, không từ cụm đường cong.** Đảo lại là sửa lỗi lặp 3
  lần. Đừng "tinh chỉnh" theo hướng cũ.
- **Một trang có thể là loại đồ thị KHÁC.** Trang 23 của catalog AC-D có trục X là
  áp VÀO, không phải lưu lượng — phân loại theo chú thích trục, nếu không thì số áp
  chảy vào tệp lưu lượng.
- **Hai họ áp vào trên cùng một ô** (1,0 MPa nét liền · 0,7 MPa nét đứt) và áp đặt
  0,5 MPa xuất hiện ở CẢ HAI. Không đưa áp vào nhãn là gộp mất một họ.
- **`layer` KHÔNG phải loại thiết bị.** Nó là cách xếp nhóm báo giá: `valve` gộp cả
  van, đế manifold, gasket, end plate. Suy loại node từ layer đã làm engine điền mã
  VAN vào node MANIFOLD. Dùng `node_type` do luật khai.
- **Lọc theo tiền tố mã là đoán.** `SY5000-GS-1` (gasket) cùng tiền tố với
  `SY5220-5MZE-C6` (van). Phân loại theo series parse ra, và `role` trong bảng tra
  thắng series.
- **`category.layer` từ crawl không dùng được để phân loại**: 48 mã BOM có layer mà
  chỉ 5 mã suy ra được duy nhất một loại, và AS (tiết lưu) còn bị xếp `electrical`.
- **Lọc mã BOM theo `series_id` parse ra, không theo chuỗi tiền tố.**
  `AR10-M5BG-N-A` bắt đầu bằng `AR` nhưng thuộc họ khác `AR-D`.
- **Bao trên (envelope) phải cắt ở `x_common`.** Quá điểm đó "max" chỉ còn trên một
  phần các đường nên nó GIẢM — tức báo sụt áp thấp hơn thật, sai về hướng nguy hiểm.

## Tải trang nhà sản xuất

Dùng `crawler/fetcher.py`, không tự viết `urllib` — nó ép ≤1 req/s mỗi host, UA
trung thực `PneuCompleteBot/0.1`, và kiểm robots trước mỗi URL.

```sh
python3 -m crawler.robots https://www.smcworld.com/products/x/global.do   # kiểm luật
python3 -m crawler.run crawl --limit 20
```

- **Không dùng `urllib.robotparser`** — nó bỏ khối `User-agent: *` thứ hai và
  url-encode dấu `*` trong đường dẫn. Dùng `crawler/robots.py`. Xem
  `docs/smc-selection-software.md` để biết số đo.
- **Không giả dạng trình duyệt.** smcworld.com chặn `ClaudeBot`, `GPTBot`, `CCBot`
  và 5 bot AI khác theo tên; crawler của dự án khai đúng danh tính riêng nên rơi vào
  nhóm `*`. Đổi UA để lách là qua mặt ý muốn của chủ site.
- **`Allow: /` không phải giấy phép bản quyền.** Nội dung tải về dùng nội bộ.
  `Content-Signal: ai-train=no, use=reference` — thiết kế theo luật nên không huấn
  luyện mô hình; đọc để tham chiếu là đúng phần `use=reference`.
- **Sau cổng đăng nhập thì dừng.** Phần mềm chọn model của SMC yêu cầu tài khoản.
  Không đăng nhập bằng tài khoản của người dùng (mật khẩu sẽ vào log), không gọi API
  vòng qua cổng dù máy chủ có thể không kiểm — ổ khoá lỏng không phải lời mời. Cách
  đúng: người dùng đọc số bằng tay vào `db/seed/_doi-chieu-mss.yaml` rồi
  `python3 tools/doi_chieu_mss.py`; hoặc xin phép nhà sản xuất.

## Không bao giờ commit / không bao giờ đóng gói

- `DOCUMENT/`, `Catalog_Tieng_Viet/`, `*.rar` — catalog SMC **có bản quyền**. Đã
  gitignore; `EXCLUDE_PARTS` trong `tools/package.py` loại khỏi bản phát hành.
- `BOM/*.xlsx` — **dữ liệu khách hàng**.
- Bảng `machine`, `bom_line` và mọi bảng `project*` bị `STRIP_TABLES` xoá khi đóng
  gói. Thêm bảng mới chứa dữ liệu khách hàng thì phải thêm vào danh sách đó.
- Tệp ghi chú/đặc tả của người dùng: `*.md` họ viết, `*.txt`, `*.html` sơ đồ tham
  khảo, `answer*.xlsx`.

Kiểm nhanh trước khi commit:

```sh
git status --short | grep -iE "DOCUMENT|Catalog|BOM/|\.rar" && echo "DỪNG: có tệp không được commit"
```
