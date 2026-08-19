"""In BOM ra terminal.

    python3 -m engine.cli "CDM2L32-500Z x5"
    python3 -m engine.cli "CDM2L32-500Z x5" --tube-total-m 60 --pressure 0.6
    python3 -m engine.cli "CDM2L32-500Z x5" "CDM2B40-150AZ x2" --cycle-s 2.0

Cờ cấu hình (ánh xạ sang khoá của DEFAULT_PROJECT trong engine/bom.py):
    --tube-total-m N   tổng mét ống cho cả máy — engine KHÔNG tự suy (mục A3-5)
    --pressure N       áp suất làm việc, MPa
    --cycle-s N        thời gian 1 chu kỳ, giây
    --voltage V        điện áp cuộn coil
    --tube-od N        đường kính ngoài ống
    --main-port S      cỡ cửa đường trục chính cho FRL (1/8, 1/4, 3/8, 1/2, 3/4)
    --frl-size N       chốt cỡ AC (10/20/25/30/40) khi cỡ cửa có ở nhiều cỡ
    --frl-lube 1       cần lubricator (mặc định không — xy-lanh CM2 dùng mỡ sẵn)
    --valve-size S     cỡ van: SY3000 / SY5000 / SY7000 / SY9000
    --valve-mount S    body_ported (cửa riêng) hoặc base_mounted (cắm manifold)
    --valve-func S     single | double | 3pos_closed | 3pos_exhaust | 3pos_pressure
                       (khai riêng cho từng xy-lanh: "MÃ x4 valve=single")
    spd=N              số speed controller mỗi xy-lanh (mặc định 2)
                       ví dụ: "CDQSG25-250DCM-M9BZ x1 valve=double spd=1"
"""
import sys

from crawler import db
from engine import bom

LAYER_ORDER = ["actuator", "valve", "air_prep", "piping", "accessory",
               "electrical", "other", "?"]
LAYER_VN = {"actuator": "ACTUATOR", "valve": "VAN", "air_prep": "XỬ LÝ KHÍ",
            "piping": "ĐƯỜNG ỐNG", "accessory": "PHỤ KIỆN",
            "electrical": "ĐIỆN / CẢM BIẾN"}


FLAGS = {"--tube-total-m": ("tube_total_m", float), "--pressure": ("pressure_mpa", float),
         "--cycle-s": ("cycle_s", float), "--voltage": ("voltage", str),
         "--tube-od": ("tube_od_mm", float), "--tube-color": ("tube_color", str),
         "--roll-length": ("tube_roll_length_m", float),
         "--main-port": ("main_line_port_size", str), "--frl-size": ("frl_size", str),
         "--frl-lube": ("frl_lubricator", lambda v: v.lower() in ("1","true","co","có")),
         "--frl-mist": ("frl_mist_separator", lambda v: v.lower() in ("1","true","co","có")),
         "--valve-size": ("valve_series_size", str),
         "--valve-mount": ("valve_mounting", str),
         "--manifold-type": ("manifold_type", str),
         "--valve-func": ("valve_function", str),
         "--manifold": ("use_manifold", lambda v: v.lower() in ("1","true","co","có"))}


def split_flags(argv):
    """Tách cờ cấu hình khỏi danh sách mã hàng."""
    items, project, i = [], {}, 0
    while i < len(argv):
        a = argv[i]
        if a in FLAGS:
            key, cast = FLAGS[a]
            project[key] = cast(argv[i + 1])
            i += 2
        else:
            items.append(a)
            i += 1
    return items, project


ITEM_OVERRIDES = {"valve": "valve_function", "mount": "valve_mounting",
                  "size": "valve_series_size",
                  "spd": "speed_controller_per_actuator"}


def parse_args(argv):
    """'CDM2L32-500Z x5' · 'CDM2L32-500Z x5 valve=single' · '…*5' · '… 5'

    Override theo từng xy-lanh vì loại van phụ thuộc chức năng cơ cấu, không phải
    loại xy-lanh — một máy thường dùng cả single, double và 3-position.
    """
    out = []
    for a in argv:
        a = a.strip()
        over = {}
        parts = a.split()
        keep = []
        for tok in parts:
            if "=" in tok:
                k, _, v = tok.partition("=")
                over[ITEM_OVERRIDES.get(k, k)] = v
            else:
                keep.append(tok)
        a = " ".join(keep)
        for sep in (" x", "x", "*", " "):
            if sep in a:
                code, _, n = a.rpartition(sep)
                if code and n.isdigit():
                    out.append((code.strip(), int(n), over))
                    break
        else:
            out.append((a, 1, over))
    return out


def show(res):
    p = res["project"]
    print("═" * 78)
    print("BOM HỆ KHÍ NÉN")
    print("═" * 78)
    print(f"  áp suất {p['pressure_mpa']} MPa · chu kỳ {p['cycle_s']} s · "
          f"{p['voltage']} · ống ø{p['tube_od_mm']} màu {p['tube_color']} · "
          f"tự động: {'có' if p['automation'] else 'không'}")

    if res["calc"]:
        print("\n" + "─" * 78)
        print("TÍNH TOÁN")
        print("─" * 78)
        for c in res["calc"]:
            if not c.get("bore_mm"):
                continue
            print(f"  {c['item']} ×{c['count']}  (ø{c['bore_mm']:.0f}, cần ø{c['rod_mm']}, "
                  f"hành trình {c['stroke_mm']} mm)")
            print(f"     lực đẩy {c['thrust_push_N']} N · lực kéo {c['thrust_pull_N']} N")
            print(f"     khí/chu kỳ {c['air_per_cycle_L']} L · tổng {c['total_flow_lpm']} "
                  f"L/min ANR · cần cấp {c['required_flow_lpm']} L/min")
            print(f"     tốc độ piston {c['piston_speed_mm_s']:.0f} mm/s")
        print(f"\n  Σ toàn hệ: {res['system']['total_flow_lpm']} L/min ANR → "
              f"cần cấp {res['system']['required_flow_lpm']} L/min")
        a = res["calc"][0].get("assumptions") or []
        if a:
            print("  giả định: " + " · ".join(a))

    print("\n" + "─" * 78)
    print("BOM")
    print("─" * 78)
    by = {}
    for l in res["lines"]:
        by.setdefault(l["layer"], []).append(l)
    for layer in LAYER_ORDER:
        if layer not in by:
            continue
        print(f"\n  ┌ {LAYER_VN.get(layer, layer.upper())}")
        for l in by[layer]:
            unit = l.get("unit") or "cái"
            conf = l.get("confidence")
            tag = "" if conf is None or conf >= 0.9 else f"  [tin cậy {conf:.0%}]"
            print(f"  │  {l['part_number']:22} ×{l['qty']:<4} {unit}{tag}")
            if l.get("rule_code"):
                print(f"  │     ← {l['rule_code']}: {l['rationale'][:100]}")
            if l.get("note"):
                print(f"  │     ghi chú: {l['note'][:96]}")
            if l.get("alternatives"):
                print(f"  │     thay thế: {', '.join(l['alternatives'])}")
        print("  └")

    if res["warnings"]:
        print("\n" + "─" * 78)
        print("CẢNH BÁO")
        print("─" * 78)
        for w in res["warnings"]:
            mark = {"error": "✗", "warn": "⚠", "info": "i"}.get(w.get("severity"), "·")
            print(f"  {mark} [{w.get('code')}] {w.get('message')}")
            print(f"      {w['rule_code']}: {w['rationale'][:104]}")

    if res["gaps"]:
        print("\n" + "─" * 78)
        print(f"CẦN BẠN QUYẾT ĐỊNH — {len(res['gaps'])} mục engine KHÔNG đoán")
        print("─" * 78)
        for g in res["gaps"]:
            print(f"  ? {g.get('rule_code') or g.get('item')}: {g['reason']}")
            if g.get("rationale"):
                print(f"      vì sao cần: {g['rationale'][:104]}")

    print("\n" + "═" * 78)
    print(f"  {len(res['lines'])} dòng BOM · {len(res['warnings'])} cảnh báo · "
          f"{len(res['gaps'])} mục cần quyết · project_id={res['project_id']}")
    print("═" * 78)


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    items, project = split_flags(argv)
    if not items:
        print(__doc__)
        return 1
    con = db.connect()
    bom.seed_rules(con)
    res = bom.build(con, parse_args(items), project)
    show(res)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
