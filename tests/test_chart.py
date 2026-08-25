"""Kiểm bộ số hoá đồ thị theo GROUND TRUTH — cổng chặn trước khi ghi YAML.

    python3 tests/test_chart.py

Ground truth ở db/seed/charts/_groundtruth-ac.yaml, lấy từ TEXT của PDF nên ĐỘC
LẬP với việc trích đường cong vector. Nhờ vậy nó bắt đúng những lỗi đã mắc:
transform sai, tỉ lệ trục sai, gán ô sai, gán model sai, TRỘN HỌ ĐỒ THỊ.

Hai phần:
  · C1..C17 trên dữ liệu THẬT — phải PASS hết.
  · ĐỐI CHỨNG ÂM: cố tình làm sai 11 kiểu, cộng một phép kiểm hàm, cổng phải BẮT ĐƯỢC. Không có phần
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


def _pg(got, gt, w):
    """Kết quả digitize của một trang trong ground truth."""
    return got.get((w.get("pdf", AC_PDF), w["page"]), {})


def _criteria(got, gt):
    """Tính C1..C17 trên một tập kết quả digitize(). Trả [(id, ok, detail)].

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

    panels = _pg(got, gt, {"page": gt["source"]["page"]}).get("panels") or []
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
        # CHỈ ô đúng họ: trang ARG/AR_M còn có ô 'áp vào→áp ra' trên cùng trang,
        # đếm cả vào thì n_panels không bao giờ khớp.
        ps = [p for p in (_pg(got, gt, w).get("panels") or [])
              if p.get("kind") == w["kind"]]
        ts = [p.get("title") for p in ps]
        n_ser = sum(1 for p in ps if p.get("series"))
        xm_ok = (all(abs(max(p["x_ticks"]) - x) <= x * 0.02
                     for p, x in zip(ps, w["x_max"]))
                 if w.get("x_max") and len(ps) == len(w["x_max"]) else True)
        ok7 &= (len(ps) == w["n_panels"] and ts == w["titles"]
                and n_ser == w["n_panels"] and xm_ok)
        det.append(f"tr{w['page']}:{n_ser}/{w['n_panels']}ô"
                   + ("" if ts == w["titles"] else " TIÊU-ĐỀ-SAI")
                   + ("" if xm_ok else " X-SAI"))
    rec("C7-tổng-quát", ok7,
        f"{len(flow_pages)} trang họ flow_outlet · " + " ".join(det))

    # ── C8: phân loại họ đồ thị ────────────────────────────────────────────
    scope = set(gt.get("in_scope_kinds") or ["flow_outlet"])
    # Xét theo TỪNG Ô, không theo họ đa số của trang: trang ARG/AR_M trộn hai họ
    # nên "họ đa số" là con số vô nghĩa (đã làm tiêu chí này báo sai một lần).
    ok8, det8, n_ok8 = True, [], 0
    for w in pages:
        kinds = _pg(got, gt, w).get("kinds") or {}
        n_want = kinds.get(w["kind"], 0)
        if w["kind"] in scope:
            need = w.get("n_panels")
            good_pg = n_want == need if need else n_want > 0
        else:
            # trang họ ngoài phạm vi: KHÔNG ô nào được nhận thành họ trong phạm vi
            good_pg = not any(kinds.get(k) for k in scope)
        ok8 &= good_pg
        n_ok8 += good_pg
        det8.append(f"tr{w['page']}:{kinds or '0ô'}" if not good_pg else "")
    rec("C8-phân-loại-họ", ok8,
        f"{n_ok8}/{len(pages)} trang đúng họ theo từng ô"
        + (" · SAI " + " ".join(x for x in det8 if x) if not ok8 else ""))

    # ── C9: an toàn — họ khác KHÔNG được sinh số ───────────────────────────
    leaked = []
    for w in pages:
        if w["kind"] in scope:
            continue
        n = sum(len(p.get("series") or [])
                for p in (_pg(got, gt, w).get("panels") or []))
        if n:
            leaked.append(f"tr{w['page']}:{n} đường")
    rec("C9-an-toàn", not leaked,
        f"0 đường lọt từ họ ngoài {sorted(scope)}" if not leaked
        else "LỌT " + " ".join(leaked))

    # ── C10: đủ hai họ áp vào, không trùng nhãn ────────────────────────────
    # Kỳ vọng theo TỪNG trang: trang ARG chỉ vẽ MỘT điều kiện áp vào (0,7 MPa,
    # ghi bằng chữ), nên áp bảng hai họ của AC lên nó là sai.
    bad10, n_panel = [], 0
    for w in flow_pages:
        fams = {float(k): sorted(v, reverse=True) for k, v in
                (w.get("families") or gt.get("inlet_families") or {}).items()}
        for p in _pg(got, gt, w).get("panels") or []:
            if p.get("kind") != w["kind"] or not p.get("series"):
                continue
            n_panel += 1
            byin = {}
            for sr in p["series"]:
                byin.setdefault(sr.get("inlet_mpa"), []).append(_setp(sr, p))
            norm = {k: sorted(v, reverse=True) for k, v in byin.items()}
            if norm != fams:
                bad10.append(f"tr{w['page']}/{p.get('title')}={norm}")
    rec("C10-đủ-đúng-họ-áp-vào", n_panel > 0 and not bad10,
        f"{n_panel - len(bad10)}/{n_panel} ô kh��p bảng áp vào/áp đặt của trang"
        + (" · SAI " + "; ".join(bad10[:2]) if bad10 else ""))

    # ── C11: áp đặt ≤ áp vào (không điều áp lên được) ──────────────────────
    bad11 = []
    for w in flow_pages:
        for p in _pg(got, gt, w).get("panels") or []:
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
        for p in _pg(got, gt, w).get("panels") or []:
            m = _re.match(r"([A-Z]+)(\d+)", p.get("title") or "")
            if not m or not p.get("series"):
                continue
            sr = next((s for s in p["series"]
                       if abs(_setp(s, p) - 0.5) < 1e-9
                       and s.get("inlet_mpa") == 1.0), None)
            if not sr:
                continue
            y = C.interp(sr["points"], 1000.0)
            if y is not None:
                # GỘP THEO CỠ THÂN. 'AC40-06-D' là AC40 thân giống bản thường,
                # chỉ khác cỡ cửa — nên xếp nó thành 'cỡ 40,5' rồi đòi đơn điệu
                # là đòi sai: phát biểu vật lý ở đây là "THÂN lớn hơn giữ áp tốt
                # hơn", không nói gì về hai bản cùng thân. Mỗi cỡ lấy giá trị
                # BẢO THỦ nhất (áp ra thấp nhất) trong các bản.
                by_fam.setdefault(m.group(1), {}).setdefault(
                    int(m.group(2)), []).append((p["title"], y))
    bad12, det12 = [], []
    for fam, sizes in sorted(by_fam.items()):
        worst = [(sz, min(v, key=lambda t: t[1])) for sz, v in sorted(sizes.items())]
        for (sa, (la, va)), (sb, (lb, vb)) in zip(worst, worst[1:]):
            if vb < va - 0.02:
                bad12.append(f"{fam}: {la}={va:.3f} > {lb}={vb:.3f}")
        det12.append(f"{fam}:{len(worst)} cỡ thân")
    rec("C12-đơn-điệu-liên-model", bool(by_fam) and not bad12,
        f"tại 1000 L/min, đặt 0,5 MPa / vào 1,0 MPa · " + " ".join(det12)
        + (" · SAI " + "; ".join(bad12[:2]) if bad12 else ""))

    # ── C13: họ sụt áp — đủ ô, đủ tiêu đề, đủ đường ────────────────────────
    drop_pages = [p for p in pages if p["kind"] == "flow_drop"]
    det13, ok13 = [], bool(drop_pages)
    for w in drop_pages:
        ps = [p for p in (_pg(got, gt, w).get("panels") or [])
              if p.get("kind") == "flow_drop"]
        ts = [p.get("title") for p in ps]
        nser = [len(p.get("series") or []) for p in ps]
        xm_ok = all(abs(max(p["x_ticks"]) - x) <= x * 0.02
                    for p, x in zip(ps, w["x_max"])) if len(ps) == len(w["x_max"]) else False
        good_pg = (len(ps) == w["n_panels"] and ts == w["titles"] and xm_ok
                   and all(n == w["curves_per_panel"] for n in nser))
        ok13 &= good_pg
        det13.append(f"tr{w['page']}:{len(ps)}ô×{set(nser) or '-'}"
                     + ("" if ts == w["titles"] else " TIÊU-ĐỀ-SAI")
                     + ("" if xm_ok else " X-SAI"))
    rec("C13-sụt-áp-đủ-ô", ok13, " ".join(det13))

    # ── C14: neo gốc — sụt áp = 0 khi lưu lượng = 0 ────────────────────────
    # Mốc neo VẬT LÝ của họ này, thay cho C4 của họ áp ra.
    bad14, tot14 = [], 0
    for w in drop_pages:
        for p in _pg(got, gt, w).get("panels") or []:
            if p.get("kind") != "flow_drop":
                continue
            xm, ym = max(p["x_ticks"]), max(p["y_ticks"])
            for sr in p.get("series") or []:
                tot14 += 1
                x0, y0 = sr["points"][0]
                if x0 > 0.02 * xm or y0 > 0.05 * ym:
                    bad14.append(f"tr{w['page']}/{p.get('title')}({x0:.0f},{y0:.4f})")
    rec("C14-neo-gốc", tot14 > 0 and not bad14,
        f"{tot14 - len(bad14)}/{tot14} đường bắt đầu ở gốc"
        + (" · SAI " + " ".join(bad14[:2]) if bad14 else ""))

    # ── C15: sụt áp KHÔNG giảm khi lưu lượng tăng ─────────────────────────
    bad15 = 0
    for w in drop_pages:
        for p in _pg(got, gt, w).get("panels") or []:
            for sr in p.get("series") or []:
                pts = sr["points"]
                if any(y1 - y2 > 0.02 * max(p["y_ticks"])
                       for (_, y1), (_, y2) in zip(pts, pts[1:])):
                    bad15 += 1
    rec("C15-sụt-áp-tăng", tot14 > 0 and bad15 == 0,
        f"{bad15}/{tot14} đường có sụt áp GIẢM khi lưu lượng tăng")

    # ── C16: đơn điệu liên-model cho họ sụt áp ────────────────────────────
    import re as _re2
    fams16 = {}
    for w in drop_pages:
        for p in _pg(got, gt, w).get("panels") or []:
            if p.get("kind") != "flow_drop" or not p.get("series"):
                continue
            m = _re2.match(r"([A-Z]+)(\d+)", p.get("title") or "")
            if not m:
                continue
            curves = [sr["points"] for sr in p["series"]]
            # x_common: nơi MỌI đường của ô còn định nghĩa. Ngoài đó, đường bao
            # là max trên MỘT SỐ điều kiện P1 chứ không phải tất cả — so hai ô ở
            # đó là so nhầm. (Bản trước so ở 0,5·x_max và báo AL40-06-D sụt áp
            # nhiều hơn AL40-D; hai đường bao thực ra CẮT nhau vì miền khác nhau.)
            x_common = min(max(x for x, _ in c) for c in curves)
            fams16.setdefault(m.group(1), {}).setdefault(
                int(m.group(2)), []).append((p["title"], x_common, C.envelope(curves)))
    # SO TỪNG CẶP KỀ NHAU, mỗi cặp một mốc riêng — KHÔNG dùng một mốc chung cho
    # cả họ. Lý do: một model nhỏ kéo mốc chung xuống chỗ mọi cỡ lớn đều bằng
    # nhau. Đo được khi thêm AF10-A (x_common 73 so với 736…4392): mốc tụt còn
    # 36,6 L/min, ở đó AF20…AF60 chênh nhau < dung sai, C16 vẫn PASS nhưng KHÔNG
    # còn bắt được phép đổi tiêu đề nữa — một tiêu chí mất răng thì vô dụng.
    bad16, det16 = [], []
    for fam, sizes in sorted(fams16.items()):
        seq = []
        for sz, v in sorted(sizes.items()):
            seq.append((sz, max(v, key=lambda t: t[1])))    # bản có dải rộng nhất
        n_cmp = 0
        for (sa, (la, xa, ea)), (sb, (lb, xb, eb)) in zip(seq, seq[1:]):
            probe = 0.5 * min(xa, xb)                       # mốc HỢP LỆ cho ĐÚNG cặp này
            va, vb = C.interp(ea, probe), C.interp(eb, probe)
            if va is None or vb is None:
                continue
            n_cmp += 1
            if vb > va + 0.005:
                bad16.append(f"{fam}@{probe:.0f}: {la}={va:.4f} < {lb}={vb:.4f}")
        det16.append(f"{fam}:{len(seq)}cỡ/{n_cmp}cặp")
    rec("C16-đơn-điệu-liên-model-sụt-áp", bool(fams16) and not bad16,
        "cỡ lớn hơn sụt áp ít hơn · " + " ".join(det16)
        + (" · SAI " + "; ".join(bad16[:2]) if bad16 else ""))

    # ── C18: cỡ cửa của mỗi ô ──────────────────────────────────────────────
    # Đồ thị được đo ở MỘT cỡ cửa, nên cỡ cửa là một phần của kết luận chọn cỡ.
    # Ba phần: đọc được hết · khớp bản đọc tay ở tr22 · không giảm theo cỡ thân.
    import re as _re3
    bad18, n18 = [], 0
    want_port = {w["title"]: w.get("port") for w in want}
    by_fam18 = {}
    for w in flow_pages:
        for p in _pg(got, gt, w).get("panels") or []:
            if p.get("kind") != "flow_outlet" or not p.get("series"):
                continue
            n18 += 1
            tag = f"tr{w['page']}/{p.get('title')}"
            if not p.get("port") or p.get("port_inch") is None:
                bad18.append(f"{tag} không đọc được cửa")
                continue
            exp = want_port.get(p.get("title"))
            if exp and p["port"] != exp:
                bad18.append(f"{tag} cửa {p['port']}≠{exp} (bản đọc tay)")
            m = _re3.match(r"([A-Z]+)(\d+)([A-Z]*)", p.get("title") or "")
            if m:
                by_fam18.setdefault(m.group(1) + m.group(3), []).append(
                    (int(m.group(2)) + (0.5 if "-06" in p["title"] else 0),
                     p["title"], p["port_inch"]))
    for fam, items in sorted(by_fam18.items()):
        items.sort()
        for a, b in zip(items, items[1:]):
            if b[2] < a[2]:
                bad18.append(f"{fam}: {a[1]}={a[2]} > {b[1]}={b[2]} (cửa giảm)")
    rec("C18-cỡ-cửa", n18 > 0 and not bad18,
        f"{n18} ô đọc được cửa, khớp bản đọc tay, không giảm theo cỡ thân"
        + (" · SAI " + "; ".join(bad18[:2]) if bad18 else ""))

    # ── C17: đường bao TRÊN — đúng thứ sẽ ghi ra YAML ──────────────────────
    # Gọi C.envelope, tức HÀM MÀ BỘ SINH DÙNG. Bản trước tôi viết một _envelope
    # riêng trong test — cổng kiểm một thứ còn YAML ghi thứ khác, nên lỗi "bao
    # trên giảm ở đuôi" lọt qua.
    bad17, n17 = [], 0
    for w in drop_pages:
        for p in _pg(got, gt, w).get("panels") or []:
            if p.get("kind") != "flow_drop" or not p.get("series"):
                continue
            env = C.envelope([sr["points"] for sr in p["series"]])
            n17 += 1
            tag = f"tr{w['page']}/{p.get('title')}"
            if len(env) < 3:
                bad17.append(f"{tag} chỉ {len(env)} điểm")
                continue
            if any(b[1] < a[1] for a, b in zip(env, env[1:])):
                bad17.append(f"{tag} bao trên GIẢM")
            if env[0][1] > 0.05 * max(p["y_ticks"]):
                bad17.append(f"{tag} không bắt đầu ở gốc")
            xc = min(max(x for x, _ in sr["points"]) for sr in p["series"])
            if env[-1][0] > xc + 1:
                bad17.append(f"{tag} vượt x_common {xc:.0f}")
    rec("C17-bao-trên-đơn-điệu", n17 > 0 and not bad17,
        f"{n17 - len(bad17)}/{n17} ô có bao trên tăng đơn điệu, neo gốc, ≤x_common"
        + (" · SAI " + "; ".join(bad17[:2]) if bad17 else ""))

    return out


def _setp(sr, panel):
    """Áp đặt của một đường = nhãn trục Y gần điểm đầu nhất."""
    yt = panel.get("y_ticks") or []
    y0 = sr["points"][0][1]
    return min(yt, key=lambda v: abs(v - y0)) if yt else y0



def negative_controls(got, gt):
    """ĐỐI CHỨNG ÂM: làm sai rồi đòi cổng phải bắt được.

    Bộ tiêu chí ở trên do tôi tự viết. Nếu nó PASS cả với dữ liệu sai thì con số
    '9/9' chẳng chứng minh gì. Bảy phép làm sai dưới đây mô phỏng đúng những lỗi
    ĐÃ THẬT SỰ MẮC khi làm phần này.
    """
    cases = []

    g = copy.deepcopy(got)                                # 1. sai hiệu chuẩn Y
    for p in g[(AC_PDF, 22)]["panels"]:
        for sr in p.get("series") or []:
            for pt in sr["points"]:
                pt[1] = round(pt[1] * 1.05, 3)
    cases.append(("sai tỉ lệ trục Y 5%", g, "C4-neo-áp-đặt"))

    g = copy.deepcopy(got)                                # 2. gán model sai
    ts = [p["title"] for p in g[(AC_PDF, 22)]["panels"]]
    for p, t in zip(g[(AC_PDF, 22)]["panels"], ts[1:] + ts[:1]):
        p["title"] = t
    cases.append(("xoay thứ tự tiêu đề", g, "C2-tiêu-đề"))

    g = copy.deepcopy(got)                                # 3. sai hiệu chuẩn X
    for p in g[(AC_PDF, 22)]["panels"]:
        for sr in p.get("series") or []:
            for pt in sr["points"]:
                pt[0] = round(pt[0] * 1.10, 1)
    cases.append(("sai tỉ lệ trục X 10%", g, "C6-trong-khung"))

    g = copy.deepcopy(got)                                # 4. trộn họ đồ thị
    for p in g[(AC_PDF, 23)]["panels"]:
        p["kind"] = "flow_outlet"
        p["series"] = [{"inlet_mpa": 1.0, "dashed": False,
                        "points": [[0.0, 0.8], [100.0, 0.7], [200.0, 0.6]]}]
    g[(AC_PDF, 23)]["kind"] = "flow_outlet"
    cases.append(("coi trang áp-vào là lưu-lượng", g, "C9-an-toàn"))

    g = copy.deepcopy(got)                                # 5. mất một họ áp vào
    ps = g[(AC_PDF, 22)]["panels"]
    ps[0]["series"] = [s for s in ps[0]["series"] if s.get("inlet_mpa") != 1.0]
    cases.append(("bỏ họ áp vào 1,0 của một ô", g, "C10-đủ-đúng-họ-áp-vào"))

    g = copy.deepcopy(got)                                # 6. ghép nét ↔ áp vào NGƯỢC
    for p in g[(AC_PDF, 22)]["panels"]:
        for sr in p.get("series") or []:
            sr["inlet_mpa"] = 0.7 if sr["inlet_mpa"] == 1.0 else 1.0
    cases.append(("ghép nét ↔ áp vào ngược", g, "C11-áp-đặt-dưới-áp-vào"))

    g = copy.deepcopy(got)                                # 7. đổi tiêu đề hai ô
    ps = g[(AC_PDF, 22)]["panels"]
    ps[0]["title"], ps[5]["title"] = ps[5]["title"], ps[0]["title"]
    cases.append(("đổi tiêu đề ô nhỏ nhất ↔ lớn nhất", g, "C12-đơn-điệu-liên-model"))

    g = copy.deepcopy(got)                                # 8. đọc sai cỡ cửa
    for p in g[(AC_PDF, 22)]["panels"]:
        if p.get("kind") == "flow_outlet":
            p["port"], p["port_code"], p["port_inch"] = "Rc1", "10", 1.0
    cases.append(("gán mọi ô cỡ cửa Rc1", g, "C18-cỡ-cửa"))

    g = copy.deepcopy(got)                                # 9. thiếu một đường sụt áp
    g[(AC_PDF, 79)]["panels"][0]["series"] = g[(AC_PDF, 79)]["panels"][0]["series"][:-1]
    cases.append(("bỏ 1 đường của ô sụt áp", g, "C13-sụt-áp-đủ-ô"))

    g = copy.deepcopy(got)                                # 9. mất mốc gốc
    for sr in g[(AC_PDF, 79)]["panels"][0]["series"]:
        for pt in sr["points"]:
            pt[1] = round(pt[1] + 0.03, 4)
    cases.append(("dịch đường sụt áp lên 0,03 MPa", g, "C14-neo-gốc"))

    g = copy.deepcopy(got)                                # 10. đảo chiều sụt áp
    for sr in g[(AC_PDF, 79)]["panels"][0]["series"]:
        ys = [y for _, y in sr["points"]][::-1]
        for pt, y in zip(sr["points"], ys):
            pt[1] = y
    cases.append(("đảo chiều đường sụt áp", g, "C15-sụt-áp-tăng"))

    g = copy.deepcopy(got)                                # 11. đổi tiêu đề ô sụt áp
    ps = [p for p in g[(AC_PDF, 79)]["panels"] if p.get("kind") == "flow_drop"]
    ps[0]["title"], ps[-1]["title"] = ps[-1]["title"], ps[0]["title"]
    cases.append(("đổi tiêu đề ô sụt áp nhỏ ↔ lớn", g, "C16-đơn-điệu-liên-model-sụt-áp"))



    print("\nĐỐI CHỨNG ÂM — cổng phải BẮT ĐƯỢC từng lỗi cố tình gieo")
    print("-" * 70)
    ok_all = True
    for name, bad, must_fail in cases:
        rs = {cid: ok for cid, ok, _ in _criteria(bad, gt)}
        caught = not rs.get(must_fail, True)
        ok_all &= caught
        print(f"  {'BẮT ĐƯỢC ' if caught else 'KHÔNG BẮT'}  {name:32} → {must_fail}")

    # ── kiểm HÀM bao trên bằng đầu vào tổng hợp ────────────────────────────
    # Không gieo được lỗi này qua dữ liệu: phép cắt tại x_common làm bao trên
    # KHÔNG THỂ giảm. Bảo vệ bằng cấu trúc thì phải kiểm chính cấu trúc đó —
    # nếu không, C17 chỉ là một tiêu chí luôn đúng.
    #   c1 dừng sớm nhưng sụt áp CAO · c2 dài hơn nhưng sụt áp THẤP
    #   không cắt → bao trên đi 0,05 (x=100) xuống 0,04 (x=500): vô nghĩa vật lý
    c1 = [[0, 0.0], [50, 0.03], [100, 0.05]]
    c2 = [[0, 0.0], [100, 0.02], [500, 0.04]]
    env = C.envelope([c1, c2])
    trunc = bool(env) and env[-1][0] <= 101
    mono = all(b[1] >= a[1] for a, b in zip(env, env[1:]))
    ok_all &= trunc and mono
    print(f"  {'ĐÚNG    ' if trunc and mono else 'SAI     '}  "
          f"{'hàm bao trên cắt tại x_common':32} → "
          f"tới x={env[-1][0] if env else '—'}, tăng đơn điệu={mono}")
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
    for w in gt["pages"]:
        # `pdf` khai riêng cho trang thuộc catalog khác (vòng B). Khoá theo CẢ HAI
        # để số trang trùng nhau giữa các catalog không lẫn.
        pdf = w.get("pdf", AC_PDF)
        try:
            got[(pdf, w["page"])] = C.digitize(pdf, w["page"])
        except Exception as e:                            # noqa: BLE001
            got[(pdf, w["page"])] = {"panels": [], "n_ok": 0, "kind": None,
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
