"""Sinh db/seed/charts/*-flow.yaml từ đồ thị catalog — CHỈ KHI ĐẠT CỔNG.

    python3 -m parsers.chart_yaml            # xem sẽ ghi gì, KHÔNG ghi
    python3 -m parsers.chart_yaml --write    # chạy cổng rồi ghi

VÌ SAO BỘ SINH TỰ GỌI CỔNG: yêu cầu đặt ra là "không được tiếp tục đoán số rồi
ghi YAML". Cách chắc chắn nhất để giữ điều đó không phải là tôi nhớ chạy kiểm
trước — mà là làm cho việc ghi KHÔNG THỂ xảy ra khi kiểm chưa đạt. Nên hàm
build() gọi tests/test_chart.py trước, thất bại thì raise.

Cổng gồm 18 tiêu chí đối chiếu ground truth (đọc từ TEXT của PDF, độc lập với việc
trích đường cong) + 12 đối chứng âm. Xem db/seed/charts/_groundtruth-ac.yaml.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parsers import pdf_chart                      # noqa: E402

OUT = ROOT / "db/seed/charts/ac-flow.yaml"
PDF = "DOCUMENT/FRL/es40-69-AC-D.pdf"
SAMPLES = 12

# Trang họ "lưu lượng → áp ra". Danh sách này PHẢI khớp `pages` trong
# db/seed/charts/_groundtruth-ac.yaml — cổng chỉ kiểm những trang khai ở đó, nên
# thêm trang vào đây mà không thêm vào ground truth là ghi số CHƯA QUA CỔNG.
FLOW_PAGES = [
    (PDF, 22),                                     # AC20-D … AC60-D
    (PDF, 103),                                    # AR20(K)-D … AR60(K)-D
    (PDF, 128),                                    # AW20(K)-D … AW60(K)-D
    ("DOCUMENT/FRL/es40-70-ARG-B.pdf", 4),         # ARG20(K)-B … ARG40(K)-B
    ("DOCUMENT/FRL/es40-72-AR_M-D.pdf", 11),       # AR20M(K)-D … AR40M(K)-D
    ("DOCUMENT/FRL/es40-74-AWM-AWD-D.pdf", 8),     # AWM/AWD — DÒ TỪ ẢNH raster
]


def expand(title):
    """'AR20(K)-D' → ['AR20-D', 'AR20K-D']. Ký hiệu catalog, không phải suy diễn.

    Catalog dùng ngoặc để gộp hai model dùng CHUNG một đồ thị: AR20(K)-D nghĩa là
    đồ thị này áp cho cả AR20-D và AR20K-D (bản có van một chiều). Không tách thì
    engine tra mã AR20K-D sẽ không thấy bảng nào.
    """
    m = re.search(r"\(([^)]*)\)", title)
    if not m:
        return [title]
    a = title[:m.start()] + title[m.end():]
    b = title[:m.start()] + m.group(1) + title[m.end():]
    return [a, b] if a != b else [a]


def slug(title):
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def collect():
    """Trích các trang lưu lượng→áp ra, trả (danh sách bảng, số điểm bị cắt)."""
    charts, clamped = [], 0
    for pdf, pg in FLOW_PAGES:
        r = pdf_chart.digitize(pdf, pg, samples=SAMPLES)
        for p in r.get("panels") or []:
            if p.get("kind") != "flow_outlet" or not p.get("series"):
                continue
            x_max = max(p["x_ticks"])
            yt = p["y_ticks"]
            series = []
            for sr in p["series"]:
                # nhãn đường = ÁP VÀO / ÁP ĐẶT. Phải có CẢ HAI: mỗi ô vẽ hai họ
                # theo áp vào (chú giải cấp trang) và áp đặt 0,5 MPa có mặt ở cả
                # hai họ. Chỉ ghi áp đặt thì tra ra số của điều kiện nào là ngẫu
                # nhiên — bản YAML đầu tiên đã mắc đúng lỗi này.
                # Áp đặt = nhãn trục Y gần điểm đầu nhất; C4 bảo đảm lệch ≤0,025.
                setp = min(yt, key=lambda v: abs(v - sr["points"][0][1]))
                inlet = sr.get("inlet_mpa")
                if inlet is None:
                    continue                  # không biết điều kiện → không ghi
                ded = []
                for x, y in sr["points"]:
                    q = [round(x, 1), round(y, 3)]
                    if ded and q[0] == ded[-1][0]:
                        ded[-1] = q
                    else:
                        ded.append(q)
                if len(ded) >= 3:
                    series.append({"label": f"{inlet:g}/{setp:g}",
                                   "inlet_mpa": inlet, "set_mpa": setp,
                                   "points": ded})
            if not series:
                continue
            clamped += p.get("trimmed_points") or 0
            series.sort(key=lambda s: (-s["inlet_mpa"], -s["set_mpa"]))
            charts.append({
                "source_kind": r.get("source") or "vector",
                "chart_id": f"frl_flow_{slug(expand(p['title'])[0])}",
                "model_label": p["title"],
                "applies_to": expand(p["title"]),
                "pdf": pdf,
                "pdf_page": pg,
                "x_max": x_max,
                "port_in": p.get("port_in"),
                "port_out": p.get("port"),
                "port_code": p.get("port_code"),
                "port_inch": p.get("port_inch"),
                "kind": "continuous",
                "series": series,
            })
    return charts, clamped


# Trang họ "lưu lượng → sụt áp". Cũng phải khớp `pages` trong ground truth.
DROP_PAGES = [
    (PDF, 79),                                     # AF20-D … AF60-D (lọc)
    (PDF, 92),                                     # AFM/AFD (tách ẩm)
    (PDF, 119),                                    # AL20-D … AL60-D (tra dầu)
    ("DOCUMENT/FRL/ES30-25-AFG-D.pdf", 4),         # AFG20-D … AFG40-06-D
    ("DOCUMENT/FRL/ES40-60-AF10-A.pdf", 2),        # AF10-A (lọc cỡ nhỏ)
]
DROP_OUT = ROOT / "db/seed/charts/frl-drop.yaml"


def collect_drop():
    """Trích ba trang sụt áp, trả danh sách bảng (mỗi model một bảng)."""
    charts = []
    for pdf, pg in DROP_PAGES:
        r = pdf_chart.digitize(pdf, pg, samples=14)
        for p in r.get("panels") or []:
            if p.get("kind") != "flow_drop" or not p.get("series"):
                continue
            env = pdf_chart.envelope([sr["points"] for sr in p["series"]])
            if len(env) < 3:
                continue
            # ĐUÔI BAO TRÊN CHẠM ĐỈNH TRỤC nghĩa là điều kiện xấu nhất bị KHUNG
            # cắt, tức sụt áp thật còn LỚN HƠN dải đồ thị. Khác hẳn với "catalog
            # thôi không vẽ nữa" — engine phải nói được hai điều đó khác nhau.
            y_max = max(p["y_ticks"])
            charts.append({
                "chart_id": f"frl_drop_{slug(expand(p['title'])[0])}",
                "model_label": p["title"],
                "applies_to": expand(p["title"]),
                "pdf": pdf,
                "pdf_page": pg,
                "x_max": max(p["x_ticks"]),
                "n_conditions": len(p["series"]),
                "ends_at_y_max": bool(env and env[-1][1] >= y_max - 0.002),
                "y_max": y_max,
                "kind": "continuous",
                "series": [{"label": "max", "points": env}],
            })
    return charts


DROP_HEAD = """\
# SỤT ÁP theo lưu lượng của lọc AF · tách ẩm AFM/AFD · tra dầu AL.
#
# ⚠ TỆP NÀY DO MÁY SINH — sửa tay sẽ bị ghi đè.
#     python3 -m parsers.chart_yaml --write
#
# ── ĐÂY LÀ ĐƯỜNG BAO TRÊN, KHÔNG PHẢI TỪNG ĐIỀU KIỆN ────────────────────────
# Mỗi ô trong catalog vẽ {NC} đường ứng với các ÁP VÀO P1 khác nhau. Nhãn P1 viết
# XOAY bên trong ô, và pdftotext tách nó thành ký tự rời — 'P','1','=','0','.3',
# 'MP','a' — nên KHÔNG có nguồn text nào đọc lại được cho chắc. Đã chọn KHÔNG gán
# nhãn theo phỏng đoán, mà ghi ĐƯỜNG BAO TRÊN: sụt áp lớn nhất trong các P1 đã vẽ.
#
# Bảo thủ đúng hướng, giống cách đã làm với dẫn nạp âm SY: thừa sụt áp thì engine
# chọn cỡ TO HƠN mức cần, chứ không bao giờ nhỏ hơn. Sai theo hướng còn lại là
# sụt áp khi nhiều xy-lanh chạy cùng lúc.
#
# ── VÌ SAO TIN ĐƯỢC ─────────────────────────────────────────────────────────
# Mốc neo VẬT LÝ của họ này: sụt áp = 0 khi lưu lượng = 0. Đo được {NANCHOR} đường
# đều bắt đầu ở gốc. Cộng với: mọi đường tăng đơn điệu, và cỡ thân lớn hơn sụt áp
# ít hơn ở cùng lưu lượng — kiểm chứng ĐỘC LẬP với từng ô (tiêu chí C13–C16).
# Cổng đầy đủ: tests/test_chart.py ({NCRIT} tiêu chí + {NNEG} đối chứng âm).
#
# ── ĐỌC THẾ NÀO ─────────────────────────────────────────────────────────────
#   điểm = [lưu lượng L/min (ANR), sụt áp MPa]
#   n_conditions = số đường P1 mà bao trên này gộp lại
#   engine.chart.frl_drop(model, lưu_lượng) — nội suy, KHÔNG ngoại suy
#   ends_at_y_max=true: đuôi bao trên CHẠM đỉnh trục, nên ngoài dải thì sụt áp
#     thật > y_max. Khác với false (catalog thôi không vẽ nữa → hoàn toàn chưa biết).
#
# ── DẢI PHỦ CÓ HẠN — nói rõ ─────────────────────────────────────────────────
# Bao trên chỉ định nghĩa tới x_common, chỗ MỌI điều kiện còn được vẽ. Với AF50-D
# đó là 3.910 trong dải trục 15.000 L/min (26%). Ngoài đó engine báo GAP chứ không
# giữ phẳng giá trị cuối: giữ phẳng là ước sụt áp THẤP hơn thực tế, mà sai theo
# hướng đó thì chọn cỡ nhỏ quá — đúng thứ phần mềm này phải tránh.

source:
  catalog: {PDF}
  pdf_page: "es40-69-AC-D: 79 (AF), 92 (AFM/AFD), 119 (AL) · ES30-25-AFG-D: 4
    (AFG). Mỗi bảng mang theo `catalog` + `pdf_page` riêng."
  table: "Flow Rate Characteristics — Pressure drop"
  note: >
    Đường bao trên của các áp vào P1 đã vẽ. Trích tự động từ vector PDF, qua cổng
    {NCRIT} tiêu chí + {NNEG} đối chứng âm. Chi tiết: db/seed/charts/_groundtruth-ac.yaml
confidence: 0.85
digitized_by: >
  parsers/chart_yaml.py — tự động từ vector PDF. Confidence thấp hơn bảng lưu
  lượng (0.9) vì đây là ĐƯỜNG BAO, không phải số của một điều kiện xác định.
axis:
  x: {{name: flow_lpm_anr, unit: "L/min (ANR)"}}
  y: {{name: pressure_drop, unit: MPa}}

charts:
"""


HEAD = """\
# Đặc trưng LƯU LƯỢNG → ÁP RA của bộ lọc-điều áp FRL (AC / AR / AW).
#
# ⚠ TỆP NÀY DO MÁY SINH — sửa tay sẽ bị ghi đè.
#     python3 -m parsers.chart_yaml --write
#
# ── VÌ SAO TIN ĐƯỢC ─────────────────────────────────────────────────────────
# Số ở đây KHÔNG phải đọc bằng mắt và KHÔNG phải đoán. Đồ thị trong catalog SMC
# là VECTOR, nên trích trực tiếp: `pdftocairo -svg` cho đường cong, `pdftotext
# -bbox-layout` cho nhãn trục kèm toạ độ. Nhãn trục hiệu chuẩn pixel → giá trị.
#
# Trước khi tệp này được ghi, bộ trích phải qua CỔNG {NC} tiêu chí đối chiếu
# ground truth ở db/seed/charts/_groundtruth-ac.yaml — ground truth lấy từ TEXT
# của PDF nên ĐỘC LẬP với việc trích đường cong — cộng {NN} đối chứng âm (cố tình
# làm sai, cổng phải bắt được). Bộ sinh TỰ GỌI cổng và từ chối ghi nếu chưa đạt:
#
#     python3 tests/test_chart.py
#
# Căn cứ vật lý của tiêu chí mạnh nhất: SMC vẽ một đường cho MỖI ÁP ĐẶT TRƯỚC, và
# mỗi đường bắt đầu (lưu lượng ≈ 0) đúng tại áp đặt của nó — một nhãn trục Y. Đo
# được 50/50 đường khớp trong ±0,025 MPa. Sai transform hay sai tỉ lệ là lệch
# hàng loạt, không thể khớp 100%.
#
# ── ĐỌC THẾ NÀO ─────────────────────────────────────────────────────────────
#   label = "ÁP VÀO / ÁP ĐẶT" [MPa].  Ví dụ "1/0.8" = áp vào 1,0 · đặt 0,8.
#   điểm = [lưu lượng L/min (ANR), áp ra MPa]
#   applies_to: catalog ghi 'AR20(K)-D' nghĩa là dùng cho CẢ AR20-D và AR20K-D
#   port_in/port_out: cỡ cửa mà đồ thị ĐƯỢC ĐO Ở. Không phải "cửa duy nhất bán ra"
#     — nhưng lắp cửa NHỎ HƠN thì đường cong này thành lạc quan (sụt áp thật nhiều
#     hơn), nên engine phải kiểm và nói ra. Series AR…M có vào ≠ ra.
#
# VÌ SAO PHẢI CÓ ÁP VÀO TRONG NHÃN: mỗi ô vẽ HAI họ đường theo chú giải cấp trang
# ("Inlet pressure: 1.0 MPa" nét liền · "0.7 MPa" nét đứt), và áp đặt 0,5 MPa có
# mặt ở CẢ HAI họ. Bản YAML đầu tiên chỉ ghi áp đặt → hai đường trùng nhãn 0,5 và
# lookup lấy đường nào là ngẫu nhiên theo thứ tự tệp. Đã sửa, và cổng có tiêu chí
# C10/C11 để lỗi đó không quay lại.
#
# Tra bằng engine.chart.lookup(chart_id, lưu_lượng, nhãn_áp_đặt) — nội suy tuyến
# tính, KHÔNG ngoại suy. Ngoài dải đã số hoá thì báo gap.
#
# ── ĐÃ CẮT NGOÀI DẢI NHÃN ───────────────────────────────────────────────────
# Vài ô có vùng vẽ rộng hơn dải nhãn trục (đo: AC40-06-D vẽ tới ~8600 L/min trong
# khi nhãn cuối là 7000). Ngoài dải nhãn là NGOẠI SUY trục nên KHÔNG giữ; phần
# tràn nhỏ của nét vẽ (≤1,09%) thì kẹp vào biên. Số điểm bị cắt lần này: {CLAMPED}.
# Trước đây gặp điểm ngoài dải là loại CẢ đường — hai ô "-06" mất sạch họ áp vào
# 1,0 MPa mà không báo gì. Im lặng thiếu dữ liệu tệ hơn báo thiếu.
#
# ── CHƯA BAO GỒM ────────────────────────────────────────────────────────────
# Catalog FRL còn hai họ đồ thị khác, bộ trích NHẬN DẠNG ĐƯỢC nhưng TỪ CHỐI số
# hoá vì chưa có ground truth riêng:
#   · pressure_char (áp vào → áp ra, tr23/104/129)
#   · flow_drop     (lưu lượng → sụt áp, lọc AFM/AFD/AFF, tr79/92/119)
# Đây là chỗ đã tránh được lỗi nặng nhất: bản trích trước báo 'tr23: 6/6 ô đạt'
# trong khi trục X của trang đó là ÁP VÀO [MPa] — vào YAML này thì engine đọc áp
# suất thành lưu lượng, không có dấu hiệu nào để phát hiện.

source:
  catalog: {PDF}
  pdf_page: "es40-69-AC-D: 22 (AC), 103 (AR), 128 (AW) · es40-70-ARG-B: 4 (ARG)
    · es40-72-AR_M-D: 11 (AR…M). Mỗi bảng mang theo `catalog` + `pdf_page` riêng."
  table: "Flow Rate Characteristics (Representative values)"
  note: >
    Trích tự động từ vector PDF, đã qua cổng {NC} tiêu chí + {NN} đối chứng âm.
    Chi tiết tiêu chí: db/seed/charts/_groundtruth-ac.yaml
confidence: 0.9
digitized_by: >
  parsers/chart_yaml.py — tự động từ vector PDF, cổng tests/test_chart.py.
  Chưa người mở catalog đối chiếu bằng mắt, nên chưa đặt 0.95.
axis:
  x: {{name: flow_lpm_anr, unit: "L/min (ANR)"}}
  y: {{name: outlet_pressure, unit: MPa}}

charts:
"""


def render(charts, clamped, n_crit, n_neg):
    out = [HEAD.replace("{PDF}", PDF).replace("{CLAMPED}", str(clamped))
           .replace("{NC}", str(n_crit)).replace("{NN}", str(n_neg))
           .replace("{{", "{").replace("}}", "}")]
    for c in charts:
        out.append(f"  - chart_id: {c['chart_id']}\n")
        out.append(f"    model_label: \"{c['model_label']}\"\n")
        out.append(f"    applies_to: [{', '.join(c['applies_to'])}]\n")
        out.append(f"    catalog: {c['pdf']}\n")
        out.append(f"    pdf_page: {c['pdf_page']}\n")
        # raster = đường cong DÒ TỪ ẢNH, không phải vector. Kém chính xác hơn nên
        # engine phải hạ tin cậy, không được coi ngang số vector.
        out.append(f"    source_kind: {c['source_kind']}\n")
        out.append(f"    x_max: {c['x_max']:g}\n")
        # Cỡ cửa mà đồ thị ĐƯỢC ĐO Ở: lắp cửa nhỏ hơn thì số lưu lượng lạc quan.
        out.append(f"    port_in: {c['port_in']}\n")
        out.append(f"    port_out: {c['port_out']}\n")
        out.append(f"    port_code: \"{c['port_code']}\"\n")
        out.append(f"    port_inch: {c['port_inch']:g}\n")
        out.append(f"    kind: {c['kind']}\n")
        out.append("    series:\n")
        for s in c["series"]:
            out.append(f"      - label: \"{s['label']}\"   "
                       f"# áp vào {s['inlet_mpa']:g} → đặt {s['set_mpa']:g} MPa\n")
            out.append(f"        inlet_mpa: {s['inlet_mpa']:g}\n")
            out.append(f"        set_mpa: {s['set_mpa']:g}\n")
            out.append("        points: ["
                       + ", ".join(f"[{x:g}, {y:g}]" for x, y in s["points"])
                       + "]\n")
    return "".join(out)


def render_drop(charts, n_crit, n_neg):
    nanchor = sum(c["n_conditions"] for c in charts)
    ncs = sorted({c["n_conditions"] for c in charts})
    out = [DROP_HEAD.replace("{PDF}", PDF)
           .replace("{NC}", " hoặc ".join(str(n) for n in ncs))
           .replace("{NANCHOR}", str(nanchor))
           .replace("{NCRIT}", str(n_crit)).replace("{NNEG}", str(n_neg))
           .replace("{{", "{").replace("}}", "}")]
    for c in charts:
        out.append(f"  - chart_id: {c['chart_id']}\n")
        out.append(f"    model_label: \"{c['model_label']}\"\n")
        out.append(f"    applies_to: [{', '.join(c['applies_to'])}]\n")
        out.append(f"    catalog: {c['pdf']}\n")
        out.append(f"    pdf_page: {c['pdf_page']}\n")
        out.append(f"    x_max: {c['x_max']:g}\n")
        out.append(f"    n_conditions: {c['n_conditions']}\n")
        out.append(f"    ends_at_y_max: {str(c['ends_at_y_max']).lower()}\n")
        out.append(f"    y_max: {c['y_max']:g}\n")
        out.append(f"    kind: {c['kind']}\n")
        out.append("    series:\n")
        for sr in c["series"]:
            out.append(f"      - label: \"{sr['label']}\"   "
                       f"# bao trên của {c['n_conditions']} điều kiện áp vào\n")
            out.append("        points: ["
                       + ", ".join(f"[{x:g}, {y:g}]" for x, y in sr["points"])
                       + "]\n")
    return "".join(out)


PC_PAGES = [(PDF, 23), (PDF, 104), (PDF, 129)]
PC_OUT = ROOT / "db/seed/charts/frl-regulation.yaml"


def collect_pc():
    """Độ ổn định điều áp: áp vào → áp ra, tại MỘT điểm làm việc."""
    charts = []
    for pdf, pg in PC_PAGES:
        r = pdf_chart.digitize(pdf, pg, samples=14)
        for p in r.get("panels") or []:
            if p.get("kind") != "pressure_char" or not p.get("series"):
                continue
            pts = p["series"][0]["points"]
            charts.append({
                "chart_id": f"frl_reg_{slug(expand(p['title'])[0])}",
                "model_label": p["title"], "applies_to": expand(p["title"]),
                "pdf": pdf, "pdf_page": pg,
                "condition": p.get("condition") or {},
                "kind": "continuous",
                "points": [[round(x, 3), round(y, 4)] for x, y in pts],
            })
    return charts


PC_HEAD = """\
# ĐỘ ỔN ĐỊNH ĐIỀU ÁP: áp vào → áp ra, của bộ điều áp FRL.
#
# ⚠ TỆP NÀY DO MÁY SINH — sửa tay sẽ bị ghi đè.
#     python3 -m parsers.chart_yaml --write
#
# ── SỐ CHỈ CÓ NGHĨA KÈM ĐIỀU KIỆN ───────────────────────────────────────────
# Đồ thị đo tại MỘT điểm làm việc, ghi bằng chữ ngay trên trang:
#     "Inlet pressure of 0.7 MPa, Outlet pressure of 0.2 MPa, Flow rate 20 L/min"
# Trôi 0,03 MPa ở lưu lượng 20 L/min KHÔNG nói gì về hành vi ở 2000 L/min. Nên
# mỗi bảng mang theo `condition`, và engine phải từ chối nếu điều kiện không hợp.
# Trang nào không đọc được điều kiện thì KHÔNG có trong tệp này (2 trang, 4 ô).
#
# ── DÙNG ĐỂ LÀM GÌ ──────────────────────────────────────────────────────────
# Cho biết áp ra trôi bao nhiêu khi áp nguồn dao động. Đo được: trôi 0,024–0,033
# MPa quanh mức đặt 0,2 khi áp vào đi từ 0,24 đến 0,99 MPa — tức bộ điều áp giữ
# khá tốt, và áp nguồn tụt trong dải đó không làm hỏng áp làm việc.
#
#   điểm = [áp vào MPa, áp ra MPa]

source:
  catalog: {PDF}
  pdf_page: "23 (AC), 104 (AR), 129 (AW)"
  table: "Pressure Characteristics (Representative values)"
confidence: 0.85
digitized_by: "parsers/chart_yaml.py — tự động từ vector PDF, cổng tests/test_chart.py"
axis:
  x: {{name: inlet_pressure, unit: MPa}}
  y: {{name: outlet_pressure, unit: MPa}}

charts:
"""


def render_pc(charts):
    out = [PC_HEAD.replace("{PDF}", PDF).replace("{{", "{").replace("}}", "}")]
    for c in charts:
        cond = c["condition"]
        out.append(f"  - chart_id: {c['chart_id']}\n")
        out.append(f"    model_label: \"{c['model_label']}\"\n")
        out.append(f"    applies_to: [{', '.join(c['applies_to'])}]\n")
        out.append(f"    catalog: {c['pdf']}\n")
        out.append(f"    pdf_page: {c['pdf_page']}\n")
        out.append(f"    condition: {{set_mpa: {cond.get('set_mpa')}, "
                   f"flow_lpm: {cond.get('flow_lpm')}, "
                   f"inlet_mpa: {cond.get('inlet_mpa')}}}\n")
        out.append(f"    kind: {c['kind']}\n")
        out.append("    series:\n      - label: \"outlet\"\n        points: ["
                   + ", ".join(f"[{x:g}, {y:g}]" for x, y in c["points"]) + "]\n")
    return "".join(out)


def build(write=False):
    """Trích + ghi. RAISE nếu cổng chưa đạt — đó là điểm chính của hàm này."""
    from tests import test_chart
    n_crit = 18
    n_neg = 12
    if test_chart.main() != 0:
        raise SystemExit(
            "CỔNG CHƯA ĐẠT → không ghi YAML. Số chưa kiểm chứng vào engine là "
            "sai cỡ FRL, mà sai cỡ FRL là sụt áp khi nhiều xy-lanh chạy.")
    charts, clamped = collect()
    text = render(charts, clamped, n_crit, n_neg)
    drops = collect_drop()
    dtext = render_drop(drops, n_crit, n_neg)
    pcs = collect_pc()
    ptext = render_pc(pcs)
    if write:
        OUT.write_text(text)
        DROP_OUT.write_text(dtext)
        PC_OUT.write_text(ptext)
        print(f"✓ ghi {PC_OUT.relative_to(ROOT)} — {len(pcs)} model")
        print(f"\n✓ ghi {OUT.relative_to(ROOT)} — {len(charts)} model, "
              f"{sum(len(c['series']) for c in charts)} đường")
        print(f"✓ ghi {DROP_OUT.relative_to(ROOT)} — {len(drops)} model, "
              f"{sum(c['n_conditions'] for c in drops)} điều kiện gộp thành bao trên")
    else:
        print(f"\n(chưa ghi) lưu lượng→áp ra: {len(charts)} model, "
              f"{sum(len(c['series']) for c in charts)} đường, {len(text)} byte")
        print(f"           lưu lượng→sụt áp: {len(drops)} model, {len(dtext)} byte")
        print("  thêm --write để ghi")
    return charts, drops


if __name__ == "__main__":
    build(write="--write" in sys.argv[1:])
