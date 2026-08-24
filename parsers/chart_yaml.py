"""Sinh db/seed/charts/*-flow.yaml từ đồ thị catalog — CHỈ KHI ĐẠT CỔNG.

    python3 -m parsers.chart_yaml            # xem sẽ ghi gì, KHÔNG ghi
    python3 -m parsers.chart_yaml --write    # chạy cổng rồi ghi

VÌ SAO BỘ SINH TỰ GỌI CỔNG: yêu cầu đặt ra là "không được tiếp tục đoán số rồi
ghi YAML". Cách chắc chắn nhất để giữ điều đó không phải là tôi nhớ chạy kiểm
trước — mà là làm cho việc ghi KHÔNG THỂ xảy ra khi kiểm chưa đạt. Nên hàm
build() gọi tests/test_chart.py trước, thất bại thì raise.

Cổng gồm 12 tiêu chí đối chiếu ground truth (đọc từ TEXT của PDF, độc lập với việc
trích đường cong) + 7 đối chứng âm. Xem db/seed/charts/_groundtruth-ac.yaml.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parsers import pdf_chart                      # noqa: E402

OUT = ROOT / "db/seed/charts/ac-flow.yaml"
PDF = "DOCUMENT/FRL/es40-69-AC-D.pdf"
PAGES = [22, 103, 128]                             # ba trang họ lưu lượng→áp ra
SAMPLES = 12


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
    """Trích ba trang, trả (danh sách bảng, ghi chú kẹp biên)."""
    charts, clamped = [], 0
    for pg in PAGES:
        r = pdf_chart.digitize(PDF, pg, samples=SAMPLES)
        for p in r.get("panels") or []:
            if not p.get("series"):
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
                "chart_id": f"frl_flow_{slug(expand(p['title'])[0])}",
                "model_label": p["title"],
                "applies_to": expand(p["title"]),
                "pdf_page": pg,
                "x_max": x_max,
                "kind": "continuous",
                "series": series,
            })
    return charts, clamped


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
  pdf_page: "22 (AC), 103 (AR), 128 (AW)"
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
        out.append(f"    pdf_page: {c['pdf_page']}\n")
        out.append(f"    x_max: {c['x_max']:g}\n")
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


def build(write=False):
    """Trích + ghi. RAISE nếu cổng chưa đạt — đó là điểm chính của hàm này."""
    from tests import test_chart
    n_crit = 12
    n_neg = 7
    if test_chart.main() != 0:
        raise SystemExit(
            "CỔNG CHƯA ĐẠT → không ghi YAML. Số chưa kiểm chứng vào engine là "
            "sai cỡ FRL, mà sai cỡ FRL là sụt áp khi nhiều xy-lanh chạy.")
    charts, clamped = collect()
    text = render(charts, clamped, n_crit, n_neg)
    if write:
        OUT.write_text(text)
        print(f"\n✓ ghi {OUT.relative_to(ROOT)} — {len(charts)} model, "
              f"{sum(len(c['series']) for c in charts)} đường")
    else:
        print(f"\n(chưa ghi) {len(charts)} model, "
              f"{sum(len(c['series']) for c in charts)} đường, {len(text)} byte")
        print("  thêm --write để ghi")
    return charts


if __name__ == "__main__":
    build(write="--write" in sys.argv[1:])
