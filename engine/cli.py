"""In BOM ra terminal.   python3 -m engine.cli "CDM2L32-500Z x5" """
import sys

from crawler import db
from engine import bom

LAYER_ORDER = ["actuator", "valve", "air_prep", "piping", "accessory",
               "electrical", "other", "?"]
LAYER_VN = {"actuator": "ACTUATOR", "valve": "VAN", "air_prep": "XỬ LÝ KHÍ",
            "piping": "ĐƯỜNG ỐNG", "accessory": "PHỤ KIỆN",
            "electrical": "ĐIỆN / CẢM BIẾN"}


def parse_args(argv):
    """'CDM2L32-500Z x5' hoặc 'CDM2L32-500Z*5' hoặc 'CDM2L32-500Z 5'"""
    out = []
    for a in argv:
        a = a.strip()
        for sep in (" x", "x", "*", " "):
            if sep in a:
                code, _, n = a.rpartition(sep)
                if code and n.isdigit():
                    out.append((code.strip(), int(n)))
                    break
        else:
            out.append((a, 1))
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
    con = db.connect()
    bom.seed_rules(con)
    res = bom.build(con, parse_args(argv))
    show(res)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
