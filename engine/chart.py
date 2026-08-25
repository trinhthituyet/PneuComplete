"""Tra cứu đồ thị/bảng đã số hoá từ catalog (mục 7 của prompt sơ đồ đấu nối).

VÌ SAO CÓ: nhiều giá trị chỉ có trong catalog dưới dạng ĐỒ THỊ hoặc BẢNG ảnh —
lưu lượng theo áp suất, dẫn nạp âm theo cỡ van, đồ thị chọn cỡ FRL. Trước đây
engine bó tay và đẩy sang `NEEDS_INPUT`, bắt người dùng tự tra catalog rồi gõ vào.

Số hoá được thì engine tự tra. Ba nguyên tắc:

  1. KHÔNG NGOẠI SUY. Ngoài khoảng đã số hoá thì báo gap, không kéo dài đường
     cong. Ngoại suy sai cỡ van là sụt áp khi nhiều xy-lanh chạy cùng lúc.
  2. MANG THEO NGUỒN. Mỗi bảng có catalog + số trang + confidence, và giá trị tra
     ra phải mang theo chúng để hiện trong rationale — giống cơ chế của rules.yaml.
  3. `needs_review: true` thì vẫn dùng được nhưng phải HẠ tin cậy và nói rõ là
     đang chờ người đối chiếu. Bảng đọc từ PDF gộp hàng thì không thể coi như đã
     chắc.
"""
import re

from engine import conf
from crawler import db

CHART_DIR = db.ROOT / "db" / "seed" / "charts"

_cache = None


def load_all():
    """Đọc mọi bảng trong db/seed/charts/. Thiếu thư mục thì trả rỗng, không lỗi."""
    global _cache
    if _cache is not None:
        return _cache
    out = {}
    if CHART_DIR.is_dir():
        for f in sorted(CHART_DIR.glob("*.yaml")):
            try:
                d = conf.load(f)
            except Exception:
                continue                      # một bảng hỏng không được chặn cả engine
            if not isinstance(d, dict):
                continue
            # MỘT TỆP có thể chứa NHIỀU bảng qua khoá `charts:` — họ FRL có 17
            # model, mỗi model một bảng, nhưng cùng một nguồn và cùng một cách
            # đọc. Tách 17 tệp thì phần "vì sao tin được" bị nhân bản 17 lần.
            # Khoá chung ở cấp tệp (source, confidence, digitized_by) được rót
            # xuống từng bảng để mỗi bảng vẫn TỰ MANG THEO NGUỒN.
            if isinstance(d.get("charts"), list):
                shared = {k: v for k, v in d.items() if k != "charts"}
                for c in d["charts"]:
                    if isinstance(c, dict) and c.get("chart_id"):
                        out[c["chart_id"]] = {**shared, **c}
            elif d.get("chart_id"):
                out[d["chart_id"]] = d
    _cache = out
    return out


def get(chart_id):
    return load_all().get(chart_id)


def _points(chart, series_label=None):
    for s in chart.get("series") or []:
        if series_label is None or s.get("label") == series_label:
            return [(p[0], p[1]) for p in (s.get("points") or [])]
    return []


def lookup(chart_id, x, series_label=None):
    """Tra y theo x. Trả (y, note) — y=None nghĩa là KHÔNG tra được.

    note luôn có nội dung để engine đưa vào rationale/detail.
    """
    ch = get(chart_id)
    if not ch:
        return None, f"chưa số hoá bảng '{chart_id}'"
    pts = _points(ch, series_label)
    if not pts:
        return None, f"bảng '{chart_id}' không có điểm dữ liệu"

    src = ch.get("source") or {}
    where = f"{src.get('catalog', '?')} trang {src.get('pdf_page', '?')}"
    conf_s = ch.get("confidence")
    tag = f"tra {where}"
    if ch.get("needs_review"):
        tag += " (CHỜ NGƯỜI ĐỐI CHIẾU)"

    # bảng rời rạc: khớp đúng khoá, không nội suy
    if ch.get("kind") == "discrete":
        for kx, ky in pts:
            if str(kx) == str(x):
                return ky, tag
        return None, f"{tag}: không có mục '{x}' trong bảng"

    # bảng liên tục: nội suy tuyến tính, KHÔNG ngoại suy
    try:
        xs = [(float(a), float(b)) for a, b in pts]
    except (TypeError, ValueError):
        return None, f"bảng '{chart_id}' có điểm không phải số"
    xs.sort()
    xv = float(x)
    if xv < xs[0][0] or xv > xs[-1][0]:
        return None, (f"{tag}: giá trị {xv} nằm NGOÀI khoảng đã số hoá "
                      f"[{xs[0][0]}–{xs[-1][0]}] — engine không ngoại suy")
    for (x1, y1), (x2, y2) in zip(xs, xs[1:]):
        if x1 <= xv <= x2:
            y = y1 if x2 == x1 else y1 + (y2 - y1) * (xv - x1) / (x2 - x1)
            note = tag + (" · nội suy 2 điểm" if x1 != xv != x2 else "")
            if conf_s:
                note += f" · tin cậy {conf_s:.0%}"
            return y, note
    return None, f"{tag}: không tra được"


# ── dùng riêng cho chọn cỡ van ───────────────────────────────────────────────

def valve_flow_capacity_lpm(size, pressure_mpa):
    """Trần lưu lượng (L/min ANR) của một cỡ van ở áp suất cho trước.

    Dùng định nghĩa ISO 6358 của dẫn nạp âm C ở chế độ chảy tắc:
        q [dm3/s ANR] = C × p1 [bar abs]
    Công thức này ghi trong db/seed/charts/sy-flow.yaml kèm nguồn.
    """
    C, note = lookup("sy_sonic_conductance", size, "capacity")
    if C is None:
        return None, note
    p1_bar_abs = float(pressure_mpa) * 10.0 + 1.013
    return 60.0 * float(C) * p1_bar_abs, f"{note} · C={C} dm³/(s·bar)"


def valve_sizes():
    """Các cỡ van đã số hoá, thứ tự từ nhỏ tới lớn theo C."""
    ch = get("sy_sonic_conductance")
    if not ch:
        return []
    return [k for k, _ in sorted(_points(ch, "capacity"), key=lambda p: float(p[1]))]


def pick_valve_size(required_lpm, pressure_mpa):
    """Cỡ van NHỎ NHẤT đủ lưu lượng. Trả (size, note) — size=None nếu không đủ dữ liệu.

    required_lpm đã bao gồm hệ số đồng thời do bom.py nhân sẵn.
    """
    if not required_lpm:
        return None, "chưa tính được lưu lượng cần cấp"
    tried = []
    for size in valve_sizes():
        cap, note = valve_flow_capacity_lpm(size, pressure_mpa)
        if cap is None:
            continue
        tried.append((size, round(cap)))
        if cap >= float(required_lpm):
            return size, (f"cần {round(float(required_lpm))} L/min ANR, {size} chịu "
                          f"{round(cap)} L/min → chọn cỡ nhỏ nhất thoả · {note}")
    if tried:
        big = tried[-1]
        return None, (f"cần {round(float(required_lpm))} L/min ANR, vượt cả cỡ lớn nhất "
                      f"đã số hoá ({big[0]} chịu {big[1]} L/min). Cần chia mạch hoặc "
                      f"số hoá thêm cỡ van lớn hơn.")
    return None, "chưa số hoá bảng lưu lượng van"


# ── dùng riêng cho chọn cỡ bộ xử lý khí FRL (AC / AR / AW) ───────────────────
#
# Trước đây `frl_size` nằm trong NEEDS_INPUT với lý do "catalog chỉ in dạng ĐỒ
# THỊ, chưa số hoá". Đã số hoá xong (db/seed/charts/ac-flow.yaml, qua cổng
# tests/test_chart.py) nên engine tự tính được, giống cỡ van.

def frl_charts(family=None):
    """Bảng FRL đã số hoá, kèm cỡ đọc từ mã. Trả [(cỡ, chart_id, nhãn)] tăng dần."""
    out = []
    for cid, ch in load_all().items():
        if not cid.startswith("frl_flow_"):
            continue
        lab = ch.get("model_label") or ""
        # Chữ SAU cỡ phải RỖNG: 'AR20M(K)-D' là series AR…M, KHÁC 'AR20(K)-D'.
        # Không tách thì tra cỡ AR có thể trả về đồ thị của AR…M — cùng cỡ thân
        # nhưng lưu lượng khác, và note sẽ dẫn sai model.
        m = re.match(r"([A-Z]+)(\d+)([A-Z]*)", lab)
        if not m:
            continue
        if family and (m.group(1) != family or m.group(3)):
            continue
        # AC40-06-D là AC40 thân lớn cửa Rc3/4 — cùng cỡ 40 nhưng lưu lượng khác.
        # Xếp sau AC40-D để "cỡ nhỏ nhất thoả" không nhảy qua bản thường.
        out.append((int(m.group(2)) + (0.5 if "-06" in lab else 0), cid, lab))
    return sorted(out)


def frl_conditions(chart_id):
    """Điều kiện đã số hoá của một bảng FRL: [(áp_vào, áp_đặt, nhãn)] tăng dần."""
    out = []
    for sr in (get(chart_id) or {}).get("series") or []:
        try:
            out.append((float(sr["inlet_mpa"]), float(sr["set_mpa"]), sr["label"]))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out)


def frl_chart_generation(family="AC"):
    """Thế hệ catalog của đồ thị đã số hoá, ví dụ 'D' từ nhãn 'AC20-D'.

    Cần vì DB có ngữ pháp cả hai thế hệ (AC-A-E và AC-D-E) nhưng DOCUMENT/ chỉ có
    đồ thị lưu lượng của thế hệ -D cho cỡ 20–60 (bản -A duy nhất là
    ES40-60-AC10-A.pdf, chỉ cho AC10). Dùng đường -D để chọn linh kiện -A là một
    GIẢ THIẾT chưa kiểm được, nên engine phải nói ra thay vì im lặng.
    """
    gens = set()
    for _, cid, lab in frl_charts(family):
        parts = (lab or "").split("-")
        if len(parts) >= 2 and len(parts[-1]) == 1 and parts[-1].isalpha():
            gens.add(parts[-1])
    return sorted(gens)[0] if len(gens) == 1 else None


def frl_drop_chart(model_or_size, family):
    """Bảng sụt áp của một phụ kiện FRL. family: AF/AL/AFM/AFD. Trả chart_id|None."""
    want = f"{family}{model_or_size}"
    for cid, ch in load_all().items():
        if not cid.startswith("frl_drop_"):
            continue
        for m in ch.get("applies_to") or []:
            if m.upper().startswith(want.upper()):
                return cid
    return None


def frl_drop(size, flow_lpm, family="AF"):
    """Sụt áp (MPa) của phụ kiện FRL cỡ `size` ở lưu lượng cho trước.

    Trả (mpa, note) — mpa=None nghĩa là KHÔNG tra được, note nói rõ vì sao.

    Số tra ra là ĐƯỜNG BAO TRÊN của các áp vào P1 catalog vẽ (xem
    db/seed/charts/frl-drop.yaml): nhãn P1 là text xoay, không đọc lại được, nên
    lấy sụt áp lớn nhất. Bảo thủ đúng hướng — thừa sụt áp thì chọn cỡ to hơn.
    """
    cid = frl_drop_chart(size, family)
    if not cid:
        return None, f"chưa số hoá đồ thị sụt áp của {family}{size}"
    y, note = lookup(cid, float(flow_lpm), "max")
    if y is not None:
        return y, note
    ch = get(cid) or {}
    pts = (ch.get("series") or [{}])[0].get("points") or []
    top = pts[-1][0] if pts else 0
    if float(flow_lpm) > top and ch.get("ends_at_y_max"):
        # Đuôi bao trên chạm đỉnh trục → sụt áp thật VƯỢT dải đồ thị. Đây là kết
        # luận dùng được: sụt quá nhiều, phải lên cỡ.
        return None, (f"{ch.get('model_label')} ở {round(float(flow_lpm))} L/min: sụt áp "
                      f"VƯỢT dải đồ thị (>{ch.get('y_max')} MPa tại >{top:.0f} L/min) "
                      f"→ cỡ này quá nhỏ")
    return None, note


def frl_port(size, family="AC"):
    """Cỡ cửa mà đồ thị lưu lượng của cỡ này ĐƯỢC ĐO Ở.

    Trả (mã_cửa, text_ra, inch_ra, text_vào) — mã=None nếu chưa số hoá.

    VÌ SAO ENGINE SUY ĐƯỢC CỠ CỬA: đồ thị đo ở một cỡ cửa xác định, nên khi engine
    đã dùng đường cong đó để chọn cỡ thân thì cỡ cửa không còn tự do — lắp nhỏ hơn
    là đường cong thành lạc quan. Đây KHÔNG phải "cỡ cửa duy nhất bán ra": catalog
    có nhiều tuỳ chọn (BOM thật có AC40B-03DG-A, cửa 3/8 trên thân 40 trong khi đồ
    thị AC40 đo ở 1/2). Nên engine đề xuất cửa của đồ thị, và nếu bạn khai nhỏ hơn
    thì cảnh báo, chứ không âm thầm dùng số lạc quan.
    """
    for sz, cid, lab in frl_charts(family):
        if int(sz) != int(size):
            continue
        ch = get(cid) or {}
        return (ch.get("port_code"), ch.get("port_out"),
                ch.get("port_inch"), ch.get("port_in"))
    return None, None, None, None


PORT_INCH = {"01": 0.125, "02": 0.25, "03": 0.375, "04": 0.5, "06": 0.75,
             "10": 1.0, "M5": 0.1}


def port_inch(code):
    """Cỡ cửa dạng mã → inch, để SO LỚN NHỎ. None nếu không biết mã."""
    return PORT_INCH.get(str(code).strip().upper())


def frl_min_size_for_port(code, family="AC"):
    """Cỡ thân NHỎ NHẤT mà đồ thị đo ở cỡ cửa ≥ `code`. Trả (cỡ, text) | (None,…).

    VÌ SAO CẦN: ngữ pháp FRL trong DB có `requires` RỖNG cho cỡ cửa, nên engine
    sinh được cả 'AC20B-10DG-D' — cửa Rc1 trên thân AC20, gần như chắc không tồn
    tại. Chưa số hoá bảng How-to-Order để biết chính xác cửa nào lắp cỡ nào, nhưng
    đồ thị cho một bản đồ cỡ thân → cỡ cửa TĂNG DẦN (đã kiểm ở C18), và bản đồ đó
    đủ để nói "cửa này chỉ xuất hiện từ cỡ N trở lên". Cảnh báo có căn cứ còn hơn
    im lặng xuất một mã không có thật.
    """
    want = port_inch(code)
    if want is None:
        return None, None
    for sz, cid, lab in frl_charts(family):
        ch = get(cid) or {}
        if (ch.get("port_inch") or 0) >= want:
            return int(sz), ch.get("port_out")
    return None, None


def pick_frl_size(required_lpm, need_mpa, supply_mpa=None, family="AC",
                  lubricator=False, mist_separator=False):
    """Cỡ FRL nhỏ nhất giữ được áp ra ≥ need_mpa tại required_lpm.

    Trả (cỡ dạng chuỗi '20'/'30'…, note) — cỡ=None nghĩa là KHÔNG kết luận được,
    và note nói rõ thiếu gì để người dùng biết phải làm gì.

    ── KHÔNG CÓ HẰNG SỐ TỰ ĐẶT ──────────────────────────────────────────────
    Bộ điều áp luôn SỤT áp khi có lưu lượng, nên "áp ra ≥ áp đặt" là bất khả:
    phải có mức sụt cho phép, và tôi không tự đặt con số đó. Cách làm ở đây: đặt
    điều áp lên BẬC KẾ TIẾP trên mức cần, rồi đòi áp ra tại lưu lượng thật vẫn
    ≥ mức cần. Bậc 0,1 MPa không do tôi chọn — đó là khoảng giữa các đường
    catalog vẽ, đọc từ nhãn trục Y.

    ── VÌ SAO CẦN ÁP NGUỒN ──────────────────────────────────────────────────
    Đồ thị có HAI họ đường theo áp vào (0,7 và 1,0 MPa) và chúng cho số KHÁC
    NHAU ở cùng áp đặt. Không điều áp LÊN được nên áp vào phải ≤ áp nguồn. Áp
    nguồn là thông số máy nén của xưởng — catalog không có, engine không suy
    được. Thiếu nó thì báo gap chứ không chọn bừa một họ.
    """
    if not required_lpm:
        return None, "chưa tính được lưu lượng cần cấp"
    cands = frl_charts(family)
    if not cands:
        return None, f"chưa số hoá đồ thị lưu lượng của họ {family}"
    conds = frl_conditions(cands[0][1])
    inlets = sorted({i for i, _, _ in conds})
    if not inlets:
        return None, "bảng FRL thiếu trường inlet_mpa — chạy lại parsers.chart_yaml"
    if supply_mpa is None:
        return None, ("thiếu ÁP NGUỒN của xưởng (áp khí máy nén cấp vào FRL). "
                      f"Đồ thị số hoá cho áp vào {', '.join(f'{v:g}' for v in inlets)}"
                      " MPa, hai họ cho số khác nhau nên không đoán được.")
    need = float(need_mpa)
    usable = [v for v in inlets if v <= float(supply_mpa) + 1e-9]
    if not usable:
        return None, (f"áp nguồn {float(supply_mpa):g} MPa thấp hơn mọi điều kiện đã "
                      f"số hoá ({', '.join(f'{v:g}' for v in inlets)} MPa) — engine "
                      "không ngoại suy đồ thị")
    inlet = max(usable)

    sets = sorted(sv for iv, sv, _ in conds if iv == inlet and sv > need + 1e-9)
    if not sets:
        top = max((sv for iv, sv, _ in conds if iv == inlet), default=0)
        return None, (f"cần giữ {need:g} MPa, nhưng ở áp vào {inlet:g} MPa đồ thị chỉ "
                      f"số hoá tới áp đặt {top:g} MPa. Giữ được {need:g} MPa dưới lưu "
                      "lượng thì phải đặt CAO HƠN mức cần → cần áp nguồn lớn hơn.")
    set_mpa = sets[0]
    label = f"{inlet:g}/{set_mpa:g}"

    # PHỤ KIỆN NỐI SAU BỘ ĐIỀU ÁP làm sụt thêm áp trước khi khí tới máy, nên phải
    # CỘNG vào yêu cầu. Tra theo ĐÚNG cỡ đang xét (AL30 cho AC30…), vì thế phải
    # tra trong vòng lặp chứ không tính trước một lần.
    addons = [(f, True) for f, on in (("AL", lubricator), ("AFM", mist_separator))
              if on]

    tried, addon_fail = [], []
    for _, cid, lab in cands:
        y, note = lookup(cid, float(required_lpm), label)
        tried.append((lab, None if y is None else round(y, 3)))
        if y is None:
            continue                    # ngoài dải đã số hoá → cỡ này nhỏ quá
        size_now = re.match(r"[A-Z]+(\d+)", lab).group(1)
        drop, dnote = 0.0, []
        blocked = None
        for fam, _ in addons:
            d, dn = frl_drop(size_now, required_lpm, fam)
            if d is None:
                blocked = dn
                break
            drop += d
            dnote.append(f"{fam}{size_now} sụt {d:.4f}")
        if blocked:
            # KHÔNG bỏ qua phụ kiện. Bỏ qua là ước áp ra CAO hơn thực tế → chọn
            # cỡ nhỏ quá, đúng hướng sai nguy hiểm nhất.
            tried[-1] = (lab, "thiếu số sụt áp phụ kiện")
            addon_fail.append(blocked)
            continue
        if drop:
            note += " · " + " + ".join(dnote) + f" → còn {y - drop:.3f} MPa"
        y -= drop
        if y >= need:
            size = re.match(r"[A-Z]+(\d+)", lab).group(1)
            smaller = ("Cỡ nhỏ hơn không đủ: "
                       + ", ".join(f"{l}={'ngoài dải' if v is None else v}"
                                   for l, v in tried[:-1])
                       if len(tried) > 1 else "")
            return size, (
                f"cần {round(float(required_lpm))} L/min ANR và giữ ≥{need:g} MPa. "
                f"Áp nguồn {float(supply_mpa):g} MPa → dùng đường áp vào {inlet:g}, "
                f"đặt {set_mpa:g} MPa (bậc kế tiếp trên mức cần). {lab} còn "
                f"{y:.3f} MPa ở lưu lượng đó → đủ. {smaller} · {note}")
    if addon_fail and len(addon_fail) == len(tried):
        # MỌI cỡ đều tắc vì phụ kiện, không phải vì bộ điều áp — nói đúng nguyên
        # nhân, nếu không người dùng đi tìm sai chỗ.
        return None, (
            f"không kết luận được vì thiếu số SỤT ÁP PHỤ KIỆN ở {round(float(required_lpm))}"
            f" L/min, không phải vì bộ điều áp. Lý do đầu tiên: {addon_fail[0]}")
    return None, (
        f"cần {round(float(required_lpm))} L/min ANR ở {need:g} MPa, vượt cả cỡ lớn "
        f"nhất đã số hoá (áp vào {inlet:g}, đặt {set_mpa:g}). Đã thử: "
        + ", ".join(f"{l}={'ngoài dải' if v is None else v}" for l, v in tried)
        + ". Cần chia mạch khí hoặc số hoá thêm cỡ lớn hơn.")
