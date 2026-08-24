"""Kiểm bộ số hoá đồ thị theo GROUND TRUTH — cổng chặn trước khi ghi YAML.

    python3 tests/test_chart.py

Ground truth ở db/seed/charts/_groundtruth-ac.yaml, lấy từ TEXT của PDF nên ĐỘC
LẬP với việc trích đường cong vector. Nhờ vậy nó bắt đúng những lỗi đã mắc:
transform sai, tỉ lệ trục sai, gán ô sai, gán model sai, TRỘN HỌ ĐỒ THỊ.

Hai phần:
  · C1..C12 trên dữ liệu THẬT — phải PASS hết.
  · ĐỐI CHỨNG ÂM: cố tình làm sai bảy kiểu, cổng phải BẮT ĐƯỢC. Không có phần
    này thì '9/9 PASS' không chứng minh gì — có thể chỉ là tiêu chí quá lỏng.

QUY TẮC: cả hai phần đạt mới được ghi db/seed/charts/ac-flow.yaml cho engine.
Sai cỡ FRL là sụt áp khi nhiều xy-lanh chạy cùng lúc, nên thà không có số.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import conf                       # noqa: E402
from parsers import pdf_chart as C            # noqa: E402

GT_PATH = Path(__file__).resolve().parent.parent / "db/seed/charts/_groundtruth-ac.yaml"
AC_PDF = "DOCUMENT/FRL/es40-69-AC-D.pdf"


def _criteria(got, gt):
    """Tính C1..C12 trên một tập kết quả digitize(). Trả [(id, ok, detail)].

    Là HÀM THUẦN trên `got` để chạy được cả trên dữ liệu cố tình làm sai — xem
    negative_controls(). Cổng nào không bao giờ FAIL được thì không phải cổng.
    """
    out = []

    def rec(cid, ok, detail=""):
        out.append((cid, ok, detail))

    want = gt["panels"]
    yt_gt = set(gt["y_ticks"])
    tol = gt["tolerance"]
    pages = gt["pages"]

    panels = got[gt["source"]["page"]].get("panels") or []
    good = [p for p in panels if p.get("series")]

    # ── C1: số ô ───────────────────────────────────────────────────────────
    rec("C1-số-ô", len(panels) == len(want),
        f"trích {len(panels)} ô, cần {len(want)}")

    # ── C2: tiêu đề ────────────────────────────────────────────────────────
    got_titles = [p.get("title") for p in panels]
    want_titles = [w["title"] for w in want]
    n_title = sum(1 for a, b in zip(got_titles, want_titles) if a == b)
    rec("C2-tiêu-đề", n_title == len(want),
        f"{n_title}/{len(want)} đúng thứ tự · trích {got_titles}")

    # ── C3: dải trục X ─────────────────────────────────────────────────────
    n_x = sum(1 for p, w in zip(panels, want)
              if (p.get("x_ticks")
                  and abs(max(p["x_ticks"]) - w["x_max"]) <= w["x_max"] * 0.02))
    rec("C3-dải-trục-X", n_x == len(want),
        f"{n_x}/{len(want)} khớp x_max "
        + str([max(p.get('x_ticks') or [0]) for p in panels]))

    # ── C4: neo áp đặt ─────────────────────────────────────────────────────
    # Mỗi đường bắt đầu đúng ÁP ĐẶT của nó, và áp đặt là một nhãn trục Y. Đây là
    # tiêu chí mạnh nhất: sai transform hay sai tỉ lệ là lệch hàng loạt.
    tot = hit = 0
    for p in good:
        for sr in p["series"]:
            tot += 1
            hit += any(abs(sr["points"][0][1] - t) <= 0.025 for t in yt_gt)
    rec("C4-neo-áp-đặt", tot > 0 and hit / tot >= 0.90,
        f"{hit}/{tot} đường bắt đầu đúng nhãn Y"
        + (f" = {hit / tot:.0%}" if tot else ""))

    # ── C5: đơn điệu ───────────────────────────────────────────────────────
    bad_mono = sum(1 for p in good for sr in p["series"]
                   if any(y2 - y1 > 0.02 for (_, y1), (_, y2)
                          in zip(sr["points"], sr["points"][1:])))
    rec("C5-đơn-điệu", tot > 0 and bad_mono == 0,
        f"{bad_mono}/{tot} đường có áp ra TĂNG khi lưu lượng tăng")

    # ── C6: trong khung ────────────────────────────────────────────────────
    # Dung sai ĐO ĐƯỢC (xem `tolerance` trong ground truth), không chọn cho vừa:
    # nét vẽ tràn qua trục ≤1,09% span, còn một đường KHUNG lệch tới 100%.
    out_box = 0
    worst = 0.0
    for p, w in zip(good, want):
        xm = w["x_max"]
        for sr in p["series"]:
            bad = False
            for x, y in sr["points"]:
                worst = max(worst, -min(x, 0) / xm, max(x - xm, 0) / xm)
                if (x < -tol["x_frac_of_max"] * xm
                        or x > xm * (1 + tol["x_frac_of_max"])
                        or y < -tol["y_mpa"] or y > max(yt_gt) + tol["y_mpa"]):
                    bad = True
            out_box += bad
    # CHỈ kiểm số ĐÃ GHI có nằm trong khung ground truth — bắt lỗi tỉ lệ trục và
    # lỗi gán số của ô này sang x_max của ô khác.
    # KHÔNG kiểm "mức tràn thô ≤ dung sai" như bản trước: mức tràn thô đang bị
    # digitize cắt về đúng dung sai, nên phép kiểm đó không bao giờ FAIL được —
    # tôi đã tự viết một tiêu chí luôn đúng. Hiệu chuẩn được kiểm bởi C3 (nhãn
    # x_max) và C4 (100% đường bắt đầu đúng nhãn Y), hai thứ đó mạnh hơn.
    raw_x = max([p.get("overshoot_x_frac", 0.0) for p in good] + [0.0])
    rec("C6-trong-khung", out_box == 0,
        f"{out_box} đường vượt khung · (tràn nét vẽ thô, chỉ để chẩn đoán: "
        f"{raw_x:.1%} dải X — phần ngoài dải nhãn đã bị CẮT, không ngoại suy)")

    # ── C7: tổng quát trên CẢ HỌ flow_outlet ───────────────────────────────
    # Bản trước liệt kê 4 trang "AC khác" — nhưng 3 trong 4 thuộc HỌ ĐỒ THỊ
    # KHÁC, nên tiêu chí đó đo sai thứ. Giờ đo đúng họ đang số hoá, và SIẾT
    # HƠN: mọi trang, mọi ô, đủ tiêu đề đúng thứ tự.
    flow_pages = [p for p in pages if p["kind"] == "flow_outlet"]
    det, ok7 = [], True
    for w in flow_pages:
        ps = got[w["page"]].get("panels") or []
        ts = [p.get("title") for p in ps]
        n_ser = sum(1 for p in ps if p.get("series"))
        ok7 &= (len(ps) == w["n_panels"] and ts == w["titles"]
                and n_ser == w["n_panels"])
        det.append(f"tr{w['page']}:{n_ser}/{w['n_panels']}ô"
                   + ("" if ts == w["titles"] else " TIÊU-ĐỀ-SAI"))
    rec("C7-tổng-quát", ok7,
        f"{len(flow_pages)} trang họ flow_outlet · " + " ".join(det))

    # ── C8: phân loại họ đồ thị ────────────────────────────────────────────
    ok8, det8 = True, []
    for w in pages:
        k = got[w["page"]].get("kind")
        if k is None:
            det8.append(f"tr{w['page']}:0ô")       # C9 lo phần an toàn
        elif k != w["kind"]:
            ok8 = False
            det8.append(f"tr{w['page']}:{k}≠{w['kind']}")
    n_kind = sum(1 for w in pages if got[w["page"]].get("kind") == w["kind"])
    rec("C8-phân-loại-họ", ok8,
        f"{n_kind}/{len(pages)} trang đúng họ"
        + (" · " + " ".join(det8) if det8 else ""))

    # ── C9: an toàn — họ khác KHÔNG được sinh số ───────────────────────────
    leaked = []
    for w in pages:
        if w["kind"] == "flow_outlet":
            continue
        n = sum(len(p.get("series") or [])
                for p in (got[w["page"]].get("panels") or []))
        if n:
            leaked.append(f"tr{w['page']}:{n} đường")
    rec("C9-an-toàn", not leaked,
        "0 đường lọt từ họ khác" if not leaked else "LỌT " + " ".join(leaked))

    # ── C10: đủ hai họ áp vào, không trùng nhãn ────────────────────────────
    fams = {float(k): sorted(v, reverse=True)
            for k, v in (gt.get("inlet_families") or {}).items()}
    bad10, n_panel = [], 0
    for w in flow_pages:
        for p in got[w["page"]].get("panels") or []:
            if not p.get("series"):
                continue
            n_panel += 1
            byin = {}
            for sr in p["series"]:
                setp = _setp(sr, p)
                byin.setdefault(sr.get("inlet_mpa"), []).append(setp)
            norm = {k: sorted(v, reverse=True) for k, v in byin.items()}
            if norm != fams:
                bad10.append(f"tr{w['page']}/{p.get('title')}={norm}")
    rec("C10-đủ-hai-họ", n_panel > 0 and not bad10,
        f"{n_panel - len(bad10)}/{n_panel} ô đủ "
        + " + ".join(f"vào {k:g}:{len(v)} đường" for k, v in sorted(fams.items()))
        + (" · SAI " + "; ".join(bad10[:2]) if bad10 else ""))

    # ── C11: áp đặt ≤ áp vào (không điều áp lên được) ──────────────────────
    bad11 = []
    for w in flow_pages:
        for p in got[w["page"]].get("panels") or []:
            for sr in p.get("series") or []:
                inl = sr.get("inlet_mpa")
                if inl is None or _setp(sr, p) > inl + 1e-9:
                    bad11.append(f"tr{w['page']}/{p.get('title')}"
                                 f" đặt {_setp(sr, p)} > vào {inl}")
    rec("C11-áp-đặt-dưới-áp-vào", not bad11,
        "mọi đường có áp đặt ≤ áp vào" if not bad11
        else f"{len(bad11)} đường vi phạm · " + "; ".join(bad11[:2]))

    # ── C12: đơn điệu liên-model — kiểm vật lý ĐỘC LẬP với từng ô ──────────
    # Cỡ lớn hơn phải giữ áp tốt hơn ở cùng lưu lượng. Bắt được lỗi gán tiêu đề
    # lẫn giữa các ô, thứ mà mọi tiêu chí "trong một ô" không thấy.
    import re as _re
    by_fam = {}
    for w in flow_pages:
        for p in got[w["page"]].get("panels") or []:
            m = _re.match(r"([A-Z]+)(\d+)", p.get("title") or "")
            if not m or not p.get("series"):
                continue
            sr = next((s for s in p["series"]
                       if abs(_setp(s, p) - 0.5) < 1e-9
                       and s.get("inlet_mpa") == 1.0), None)
            if not sr:
                continue
            y = _interp(sr["points"], 1000.0)
            if y is not None:
                key = m.group(1)
                by_fam.setdefault(key, []).append(
                    (int(m.group(2)) + (0.5 if "-06" in p["title"] else 0),
                     p["title"], y))
    bad12, det12 = [], []
    for fam, items in sorted(by_fam.items()):
        items.sort()
        for a, b in zip(items, items[1:]):
            if b[2] < a[2] - 0.02:
                bad12.append(f"{fam}: {a[1]}={a[2]:.3f} > {b[1]}={b[2]:.3f}")
        det12.append(f"{fam}:{len(items)} cỡ")
    rec("C12-đơn-điệu-liên-model", bool(by_fam) and not bad12,
        f"tại 1000 L/min, đặt 0,5 MPa / vào 1,0 MPa · " + " ".join(det12)
        + (" · SAI " + "; ".join(bad12[:2]) if bad12 else ""))

    return out


def _setp(sr, panel):
    """Áp đặt của một đường = nhãn trục Y gần điểm đầu nhất."""
    yt = panel.get("y_ticks") or []
    y0 = sr["points"][0][1]
    return min(yt, key=lambda v: abs(v - y0)) if yt else y0


def _interp(pts, x):
    """Nội suy tuyến tính, KHÔNG ngoại suy. Trả None nếu x ngoài dải."""
    if not pts or x < pts[0][0] or x > pts[-1][0]:
        return None
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if x1 <= x <= x2:
            return y1 if x2 == x1 else y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    return None


def negative_controls(got, gt):
    """ĐỐI CHỨNG ÂM: làm sai rồi đòi cổng phải bắt được.

    Bộ tiêu chí ở trên do tôi tự viết. Nếu nó PASS cả với dữ liệu sai thì con số
    '9/9' chẳng chứng minh gì. Bảy phép làm sai dưới đây mô phỏng đúng những lỗi
    ĐÃ THẬT SỰ MẮC khi làm phần này.
    """
    cases = []

    g = copy.deepcopy(got)                                # 1. sai hiệu chuẩn Y
    for p in g[22]["panels"]:
        for sr in p.get("series") or []:
            for pt in sr["points"]:
                pt[1] = round(pt[1] * 1.05, 3)
    cases.append(("sai tỉ lệ trục Y 5%", g, "C4-neo-áp-đặt"))

    g = copy.deepcopy(got)                                # 2. gán model sai
    ts = [p["title"] for p in g[22]["panels"]]
    for p, t in zip(g[22]["panels"], ts[1:] + ts[:1]):
        p["title"] = t
    cases.append(("xoay thứ tự tiêu đề", g, "C2-tiêu-đề"))

    g = copy.deepcopy(got)                                # 3. sai hiệu chuẩn X
    for p in g[22]["panels"]:
        for sr in p.get("series") or []:
            for pt in sr["points"]:
                pt[0] = round(pt[0] * 1.10, 1)
    cases.append(("sai tỉ lệ trục X 10%", g, "C6-trong-khung"))

    g = copy.deepcopy(got)                                # 4. trộn họ đồ thị
    for p in g[23]["panels"]:
        p["kind"] = "flow_outlet"
        p["series"] = [{"inlet_mpa": 1.0, "dashed": False,
                        "points": [[0.0, 0.8], [100.0, 0.7], [200.0, 0.6]]}]
    g[23]["kind"] = "flow_outlet"
    cases.append(("coi trang áp-vào là lưu-lượng", g, "C9-an-toàn"))

    g = copy.deepcopy(got)                                # 5. mất một họ áp vào
    ps = g[22]["panels"]
    ps[0]["series"] = [s for s in ps[0]["series"] if s.get("inlet_mpa") != 1.0]
    cases.append(("bỏ họ áp vào 1,0 của một ô", g, "C10-đủ-hai-họ"))

    g = copy.deepcopy(got)                                # 6. ghép nét ↔ áp vào NGƯỢC
    for p in g[22]["panels"]:
        for sr in p.get("series") or []:
            sr["inlet_mpa"] = 0.7 if sr["inlet_mpa"] == 1.0 else 1.0
    cases.append(("ghép nét ↔ áp vào ngược", g, "C11-áp-đặt-dưới-áp-vào"))

    g = copy.deepcopy(got)                                # 7. đổi tiêu đề hai ô
    ps = g[22]["panels"]
    ps[0]["title"], ps[5]["title"] = ps[5]["title"], ps[0]["title"]
    cases.append(("đổi tiêu đề ô nhỏ nhất ↔ lớn nhất", g, "C12-đơn-điệu-liên-model"))

    print("\nĐỐI CHỨNG ÂM — cổng phải BẮT ĐƯỢC từng lỗi cố tình gieo")
    print("-" * 70)
    ok_all = True
    for name, bad, must_fail in cases:
        rs = {cid: ok for cid, ok, _ in _criteria(bad, gt)}
        caught = not rs.get(must_fail, True)
        ok_all &= caught
        print(f"  {'BẮT ĐƯỢC ' if caught else 'KHÔNG BẮT'}  {name:32} → {must_fail}")
    return ok_all


def main():
    if not Path(AC_PDF).exists():
        print("BỎ QUA: không có DOCUMENT/ (catalog có bản quyền, không đóng gói)")
        return 0
    gt = conf.load(GT_PATH)

    print("KIỂM BỘ SỐ HOÁ ĐỒ THỊ theo ground truth")
    print("=" * 70)
    print(f"nguồn: {gt['source']['pdf']} trang {gt['source']['page']}\n")

    # Trích MỘT LẦN cho mọi trang trong ground truth — dùng lại cho C1..C9.
    got = {}
    for pg in [p["page"] for p in gt["pages"]]:
        try:
            got[pg] = C.digitize(AC_PDF, pg)
        except Exception as e:                            # noqa: BLE001
            got[pg] = {"panels": [], "n_ok": 0, "kind": None,
                       "error": f"{type(e).__name__}: {e}"}

    rows = _criteria(got, gt)
    for cid, ok, detail in rows:
        print(f"  {'PASS' if ok else 'FAIL'}  {cid:16} {detail}")
    n_pass = sum(1 for _, ok, _ in rows if ok)

    neg_ok = negative_controls(got, gt)

    print()
    print("=" * 70)
    print(f"{n_pass}/{len(rows)} tiêu chí PASS · đối chứng âm "
          f"{'ĐẠT' if neg_ok else 'KHÔNG ĐẠT'}")
    if n_pass == len(rows) and neg_ok:
        print("→ ĐẠT CỔNG: được phép sinh db/seed/charts/ac-flow.yaml")
        print("  CHƯA BAO GỒM (xem `gaps` trong ground truth):")
        for g in gt.get("gaps") or []:
            print(f"    · {' '.join(g.split())}")
        return 0
    print("→ CHƯA ĐẠT: KHÔNG ghi YAML cho engine. "
          "Số chưa kiểm chứng vào engine là sai cỡ FRL.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
