"""Cây dự án khí nén: quan hệ cha–con theo ĐƯỜNG DẪN KHÍ và mối lắp thật.

VÌ SAO CÓ TỆP NÀY: cây thay canvas kéo dây. Cây khớp đúng quan hệ vật lý nên
người dùng không phải vẽ dây, và mỗi quan hệ cha–con cho engine suy được thuộc
tính của con — đó là cách giảm số thông tin phải nhập.

CÂY CHUẨN — đi theo dòng khí, không theo cách nhóm trên bản vẽ:

    FRL (nguồn chung)
    └── Manifold                       1 cái cho cả máy, KHÔNG phải mỗi van 1 đế
        ├── Van SV1                    ← van CẮM LÊN manifold
        │   └── Xy-lanh CDM2L32-500Z   ← CHỈ CẦN NHẬP MÃ NÀY
        │       ├── Tiết lưu cửa A     ← vặn VÀO cửa xy-lanh
        │       └── Tiết lưu cửa B
        ├── Van SV2 → ...
        └── Giảm âm                    ← gắn cửa xả CỦA MANIFOLD, xả là chung

BA QUAN HỆ NÀY ĐO ĐƯỢC, KHÔNG PHẢI QUY ƯỚC:

1. TIẾT LƯU LÀ CON CỦA XY-LANH
   AS2201F-01-06SA : air_in  = ren MALE   R 1/8
   CDM2L32-500Z    : air_port= ren FEMALE Rc 1/8 (qty 2)
   → tiết lưu vặn trực tiếp vào cửa xy-lanh. Đặt đúng cha thì CỠ REN suy được
   từ cửa xy-lanh; đặt ngang hàng thì phải nhập tay.

2. MANIFOLD LÀ CHA CỦA VAN, VÀ CHỈ CÓ MỘT
   BOM thật: máy 23-432 có 11 van → 1 × SS5Y5-20-12 (12 station) + 12 gasket
             + 4 end plate. Máy 24-236: 12 van → 1 × SS5Y5-10SVA-13B-C6A-NA.
   → mỗi van một đế rời là sai: BOM sẽ thừa ~9 dòng đế và thiếu gasket/end plate.

3. GIẢM ÂM GẮN Ở MANIFOLD, KHÔNG PHẢI MỖI VAN
   BOM thật: AN15-02 ×2 cho 11 van. Trên manifold xả là CHUNG.
   → mỗi van một giảm âm sẽ thừa ~7 dòng.

Cây lưu vào project_graph (cùng bảng với bản canvas cũ) và chuyển sang dạng
nodes+edges bằng to_graph() để dùng lại nguyên bộ resolver đã có.
"""
import json

from engine import graph as G

# ── Quan hệ cha–con hợp lệ ───────────────────────────────────────────────────
# {loại_con: (các loại cha hợp lệ, lý do lấy từ đâu)}
# Đây là DỮ LIỆU, không phải if/else rải rác — thêm họ thiết bị mới là thêm dòng.
PARENT_OF = {
    "manifold":         (("frl", "regulator", None),
                         "manifold nhận khí từ nguồn"),
    "valve":            (("manifold", "frl", "regulator", None),
                         "van cắm lên manifold, hoặc đi rời lấy khí từ nguồn"),
    "cylinder":         (("valve",),
                         "van điều khiển xy-lanh — cạnh pneumatic_control"),
    "speed_controller": (("cylinder", "custom"),
                         "AS…F air_in ren MALE R1/8 vặn vào air_port xy-lanh "
                         "ren FEMALE Rc1/8 — đo từ interfaces.yaml"),
    "silencer":         (("manifold", "valve", "custom"),
                         "BOM thật AN15-02 ×2 cho 11 van → gắn cửa xả CHUNG của "
                         "manifold; chỉ gắn lên van khi van đi rời"),
    # ── QUAN HỆ THẬT CÒN THIẾU ──────────────────────────────────────────────
    # Bạn báo "quá ít lựa chọn khi thêm con". Đo được: 8/14 loại node KHÔNG thêm
    # được gì. Trong đó có những mối nối vật lý hiển nhiên đang bị chặn:
    #   · ống cắm vào ĐẦU ONE-TOUCH của tiết lưu (AS…F có sẵn one-touch) và của
    #     đầu nối KQ2 — đo từ part_interface: kind='onetouch'
    #   · đầu nối ở ĐẦU KIA của đoạn ống
    #   · thiết bị ngoài catalog ('custom') có thể có phụ kiện riêng của nó; chặn
    #     nó là buộc người dùng đặt phụ kiện sai chỗ rồi normalize() lại dịch đi
    "fitting":          (("cylinder", "valve", "manifold", "frl", "regulator",
                          "tubing", "speed_controller", "custom", None),
                         "đầu nối vào bất cứ cửa ren nào, hoặc nối tiếp đoạn ống"),
    "tubing":           (("valve", "manifold", "frl", "cylinder",
                          "speed_controller", "fitting", "custom", None),
                         "ống cắm vào cửa one-touch của tiết lưu/đầu nối, hoặc "
                         "nối giữa các cửa"),
    "sensor":           (("cylinder", "custom", None),
                         "cảm biến gắn rãnh xy-lanh"),
    # Floating joint vặn vào REN ĐẦU CẦN, nên chỉ có một cha hợp lệ: xy-lanh.
    # Luật R-JOINT-01 chỉ áp cho xy-lanh ren đầu cần NGOÀI (rod_end_thread_male).
    "joint":            (("cylinder", "custom"),
                         "floating joint vặn vào ren đầu cần xy-lanh"),
    # Gasket + end plate là phụ kiện CỦA ĐẾ, không của van: catalog ghi "When
    # ordering a valve individually, the base gasket is not included".
    "manifold_part":    (("manifold",),
                         "gasket/end plate lắp trên đế manifold"),
    "regulator":        (("frl", "manifold", None), "điều áp trên đường khí"),
    # PLC không nằm trên đường khí, nhưng phải ĐẶT ĐƯỢC vào sơ đồ. Trước đây khai
    # ((None,),) nghĩa là chỉ được làm GỐC — mà gốc luôn là nguồn khí, nên thực tế
    # KHÔNG BAO GIỜ thêm được node PLC. Đo được khi làm yêu cầu (4): danh sách "thêm
    # con" của mọi loại đều không có PLC, và vì thế đường suy điện áp coil từ node
    # PLC (graph.resolve bước 4) chưa bao giờ dùng được từ giao diện cây.
    # Gốc đóng vai TỦ/MÁY cho thiết bị không thuộc đường khí — quan hệ CHỨA, không
    # phải quan hệ dòng khí. Nối tới van bằng LIÊN KẾT electrical_signal.
    "plc":              (("frl", "custom", None),
                         "PLC nằm trong máy nhưng không trên đường khí; nối tới van "
                         "bằng liên kết tín hiệu điện"),
    "frl":              ((None,), "nguồn khí là gốc cây"),
    "custom":           (("cylinder", "valve", "manifold", "frl", "custom", None),
                         "thiết bị ngoài catalog — gắn đâu cũng được"),
}

# Loại nào chỉ được có MỘT trong cả máy.
SINGLETON = {
    "manifold": "BOM thật dùng 1 manifold nhiều station cho cả máy "
                "(23-432: 11 van → 1×SS5Y5-20-12; 24-236: 12 van → 1 đế)",
}

# Con mà engine TỰ SINH — người dùng không phải tạo tay.
# Đây là chỗ thực hiện yêu cầu "ít thông tin nhất": nhập mã xy-lanh là đủ.
AUTO_CHILDREN = {
    "cylinder": [("speed_controller", "Tiết lưu cửa A"),
                 ("speed_controller", "Tiết lưu cửa B")],
}


def walk(node, parent=None, depth=0):
    yield node, parent, depth
    for c in node.get("children") or []:
        yield from walk(c, node, depth + 1)


def find(root, nid):
    for n, _, _ in walk(root):
        if n.get("id") == nid:
            return n
    return None


def parent_of(root, nid):
    for n, p, _ in walk(root):
        if n.get("id") == nid:
            return p
    return None


# ── Kiểm và sửa cây ──────────────────────────────────────────────────────────

def validate(root):
    """Trả list vấn đề dạng 3 phần. KHÔNG tự sửa — sửa là việc của normalize()."""
    problems = []
    counts = {}
    for n, p, _ in walk(root):
        t = n.get("type")
        counts[t] = counts.get(t, 0) + 1
        rule = PARENT_OF.get(t)
        if not rule:
            continue
        allowed, why = rule
        ptype = p.get("type") if p else None
        if ptype not in allowed:
            problems.append({
                "rule_code": "T-PARENT-01", "severity": "warn",
                "node": n.get("id"), "what": f"{t} đặt sai chỗ",
                "field": "parent",
                "fix": f"Chuyển '{n.get('name') or t}' làm con của "
                       f"{' hoặc '.join(str(a or 'gốc cây') for a in allowed)}",
                "detail": why,
            })
    # Có manifold mà van nằm ngoài → BÁO, không tự dịch. Van đi rời là thiết kế
    # hợp lệ (BOM 23-432 có VT307 đi rời), nên đây là quyết định của người dùng.
    mfd = [n for n, _, _ in walk(root) if n.get("type") == "manifold"]
    if mfd:
        loose = [n for n, pp, _ in walk(root)
                 if n.get("type") == "valve" and (pp or {}).get("type") != "manifold"]
        if loose:
            problems.append({
                "rule_code": "T-MFD-01", "severity": "warn", "node": None,
                "what": f"{len(loose)} van nằm ngoài manifold",
                "field": "parent",
                "fix": "Kéo các van vào trong manifold, hoặc bỏ manifold nếu van đi rời",
                "detail": "Van cắm lên manifold thì mới tính đủ station, gasket và "
                          "end plate. Van đi rời vẫn hợp lệ (BOM 23-432 có VT307 đi "
                          "rời) — engine không tự dịch vì đây là quyết định thiết kế.",
            })

    for t, why in SINGLETON.items():
        if counts.get(t, 0) > 1:
            problems.append({
                "rule_code": "T-SINGLE-01", "severity": "warn",
                "node": None, "what": f"có {counts[t]} {t}, chỉ nên có 1",
                "field": t,
                "fix": f"Gộp về 1 {t} nhiều station",
                "detail": why,
            })
    return problems


def normalize(root, links=None):
    """Chuyển node đặt sai về đúng cha. Trả (root, list mô tả đã sửa gì).

    Sửa TƯỜNG MINH và báo ra, không im lặng: người dùng phải biết cây họ nhập đã
    bị dịch chỗ, nếu không họ sẽ tưởng mình khai sai.

    LIÊN KẾT BẠN KHAI THẮNG PHÉP ĐOÁN. Đo được khi làm yêu cầu (4): đặt xy-lanh XL3
    ở gốc rồi khai liên kết "van SV3 điều khiển XL3" → hàm này vẫn dịch XL3 về van
    ĐẦU TIÊN (SV1) vì nó chỉ lấy "node hợp lệ đầu tiên gặp được". Kết quả: bản đồ
    van↔xy-lanh nói XL3 do CẢ SV1 và SV3 điều khiển — hai câu trái nhau, và cỡ van
    của SV1 bị tính thêm lưu lượng của một xy-lanh không thuộc nó.
    Nên khi có liên kết chỉ đúng một cha hợp lệ thì đi theo liên kết đó.
    """
    fixed = []
    # {id node: các id nối tới nó bằng liên kết} — hai chiều, vì cha có thể ở đầu
    # nào cũng được (control: van→xy-lanh · mount: van→manifold)
    peers = {}
    for l in links or []:
        a, b = l.get("from"), l.get("to")
        if a and b:
            peers.setdefault(a, []).append(b)
            peers.setdefault(b, []).append(a)

    def detach(target):
        for n, p, _ in walk(root):
            if n is target and p:
                p["children"] = [c for c in p["children"] if c is not target]
                return p
        return None

    changed = True
    while changed:
        changed = False
        for n, p, _ in list(walk(root)):
            t = n.get("type")
            rule = PARENT_OF.get(t)
            if not rule or p is None:
                continue
            allowed, _ = rule
            if p.get("type") in allowed:
                continue
            # (1) LIÊN KẾT BẠN KHAI trước mọi phép đoán
            cand, why = None, ""
            for pid in peers.get(n.get("id")) or []:
                m = find(root, pid)
                if m is not None and m is not n and m.get("type") in allowed:
                    cand, why = m, " (theo liên kết bạn khai)"
                    break
            # (2) tìm cha hợp lệ: ưu tiên anh em ngay cạnh, rồi mới lên trên
            for sib in (p.get("children") or []) if cand is None else []:
                if sib is not n and sib.get("type") in allowed:
                    cand = sib
                    break
            if cand is None:
                for m, _, _ in walk(root):
                    if m is not n and m.get("type") in allowed:
                        cand = m
                        break
            if cand is None:
                continue
            detach(n)
            cand.setdefault("children", []).append(n)
            fixed.append(f"'{n.get('name') or t}' → con của "
                         f"'{cand.get('name') or cand.get('type')}'{why}")
            changed = True
            break
    return root, fixed


# ── Cây → nodes/edges để dùng lại resolver đã có ─────────────────────────────

# Quan hệ cha→con dịch thành loại cạnh nào.
EDGE_FOR = {
    ("valve", "cylinder"): "pneumatic_control",
    ("manifold", "valve"): "mechanical_mount",
    ("frl", "manifold"): "pneumatic_supply",
    ("frl", "valve"): "pneumatic_supply",
    ("frl", "regulator"): "pneumatic_supply",
    ("regulator", "valve"): "pneumatic_supply",
    ("regulator", "manifold"): "pneumatic_supply",
    ("manifold", "silencer"): "pneumatic_supply",
    ("cylinder", "speed_controller"): "pneumatic_control",
    ("plc", "valve"): "electrical_signal",
}


def to_graph(root, links=None):
    """Cây (+ liên kết chéo) → {nodes, edges}.

    Cạnh CHA–CON suy từ cấu trúc, người dùng không vẽ dây. Cạnh CHÉO là `links` —
    thứ mà cây một-cha không diễn đạt được (xem docstring LINK_DOMAIN).
    """
    nodes, edges = [], []
    for n, p, _ in walk(root):
        nodes.append({
            "id": n["id"], "group": n.get("type"), "code": n.get("code") or None,
            "label": n.get("name") or None, "qty": int(n.get("qty") or 1),
            "manual": bool(n.get("manual")), "note": n.get("note"),
            "overrides": n.get("overrides") or {}, "attrs": n.get("attrs") or {},
            "ports": n.get("ports") or [],
        })
        if p:
            kind = EDGE_FOR.get((p.get("type"), n.get("type")))
            if kind:
                edges.append({"id": f"e_{p['id']}_{n['id']}", "from": p["id"],
                              "to": n["id"], "from_port": None, "to_port": None,
                              "kind": kind})
    # Liên kết TRÙNG cạnh cha–con thì bỏ. Xảy ra thật: khai liên kết "SV3 điều
    # khiển XL3" rồi normalize() dịch XL3 về đúng con của SV3 theo chính liên kết
    # đó — giữ cả hai thì control_map() đếm SV3 hai lần.
    have = {(e["from"], e["to"], e["kind"]) for e in edges}
    for l in links or []:
        if (l.get("from"), l.get("to"), l.get("kind")) in have:
            continue
        edges.append({"id": l.get("id") or f"l_{l['from']}_{l['to']}",
                      "from": l["from"], "to": l["to"],
                      "from_port": l.get("from_port"), "to_port": l.get("to_port"),
                      "kind": l["kind"], "link": True, "note": l.get("note")})
    return {"nodes": nodes, "edges": edges}


# ── LIÊN KẾT CHÉO: thứ cây một-cha KHÔNG diễn đạt được ────────────────────────
#
# Bạn yêu cầu "thêm/bớt thiết bị ở bất kỳ vị trí nào và liên kết chúng giữa các
# trạm khác nhau, càng linh hoạt càng tốt".
#
# VÌ SAO KHÔNG BỎ CÂY ĐI CHO LINH HOẠT: cây là chỗ engine suy thuộc tính của con
# từ cha (cỡ ren tiết lưu lấy từ cửa xy-lanh). Bỏ cây là quay lại canvas kéo dây,
# tức bắt người dùng vẽ mọi thứ. Nên giữ cây làm XƯƠNG SỐNG và thêm liên kết cho
# đúng ba việc mà cây không làm được — và cả ba đều CÓ TÁC DỤNG THẬT ngay, vì
# graph.resolve() đã đọc cạnh từ trước:
#   1. pneumatic_control  van trạm này điều khiển xy-lanh trạm khác
#                         → control_map() → gán đúng mã van cho từng xy-lanh
#   2. electrical_signal   PLC cấp tín hiệu cho van ở nhiều trạm
#                         → điện áp coil suy từ node PLC
# mechanical_mount cũng nhận, cho quan hệ gá đặt không theo đường khí.
#
# GIỚI HẠN ĐÃ ĐO, KHÔNG PHẢI CHƯA LÀM: pneumatic_supply nhận được nhưng KHÔNG tạo
# ra vùng khí thứ hai. Cây có ĐÚNG MỘT gốc, và mọi node đều có đường lên gốc, nên
# supply_zones() luôn ra 1 vùng — liên kết chỉ THÊM được kết nối, không cắt được
# cái sẵn có. Đã thử ba cách (nhánh regulator · nguồn thứ hai khai bằng node
# custom · chèn thêm đế manifold): cả ba đều ra 1 vùng.
# Máy hai nhánh khí độc lập hiện chỉ khai được qua payload {graph} (nodes+edges
# tuỳ ý) — xem tests/test_graph.py::test_hai_vung_khi_thi_bao_thieu. Muốn khai từ
# giao diện cây thì phải cho gốc là ĐƯỜNG KHÍ NHÀ MÁY và bộ FRL thành con, tức đổi
# hình cây; chưa làm, và không giả vờ là đã làm.
#
# KIỂM MIỀN TÍN HIỆU: mỗi loại liên kết đòi hai đầu phải CÓ cổng thuộc miền đó,
# đọc từ GROUPS[...]["ports"] — không phải bảng cặp-loại viết tay. Nhờ vậy "nối
# tín hiệu điện vào ống khí" bị chặn bằng chính dữ liệu cổng đã có.
LINK_DOMAIN = {
    "pneumatic_control": "pneumatic",
    "pneumatic_supply": "pneumatic",
    "electrical_signal": "electrical",
    "mechanical_mount": "mechanical",
}


def _domains(ntype):
    return {p.get("kind") for p in (G.GROUPS.get(ntype) or {}).get("ports") or []}


def prune_links(root, links):
    """Bỏ liên kết trỏ tới node đã xoá. Trả (còn lại, [mô tả đã bỏ gì]).

    XOÁ NODE thì liên kết của nó thành trỏ vào hư không. Bỏ IM LẶNG là người dùng
    tưởng vẫn còn nối; giữ lại thì to_graph() sinh cạnh trỏ vào id không tồn tại và
    resolve() gom vùng khí sai.
    """
    ids = {n.get("id") for n, _, _ in walk(root)}
    keep, dropped = [], []
    for l in links or []:
        if l.get("from") in ids and l.get("to") in ids:
            keep.append(l)
        else:
            missing = [x for x in (l.get("from"), l.get("to")) if x not in ids]
            dropped.append(f"{l.get('from')}→{l.get('to')} (đã xoá: "
                           + ", ".join(str(m) for m in missing) + ")")
    return keep, dropped


def validate_links(root, links):
    """Trả list vấn đề dạng 3 phần. KHÔNG tự sửa."""
    problems = []
    by_id = {n.get("id"): n for n, _, _ in walk(root)}
    seen = set()
    for l in links or []:
        a, b, kind = l.get("from"), l.get("to"), l.get("kind")
        tag = f"{a}→{b}"

        def bad(what, fix, detail):
            problems.append({"rule_code": "T-LINK-01", "severity": "warn",
                             "node": a, "what": what, "field": "link",
                             "fix": fix, "detail": detail})
        if a == b:
            bad("liên kết nối node với chính nó", "Xoá liên kết này",
                "Một thiết bị không tự cấp khí cho chính nó.")
            continue
        if kind not in LINK_DOMAIN:
            bad(f"loại liên kết '{kind}' không có thật",
                "Chọn lại loại: " + ", ".join(sorted(LINK_DOMAIN)),
                "Loại liên kết dùng chung từ vựng với cạnh cha–con "
                "(graph.EDGE_KINDS) để resolve() hiểu được.")
            continue
        if (a, b, kind) in seen:
            bad(f"liên kết {tag} bị khai hai lần", "Xoá bản trùng",
                "Khai hai lần thì vùng khí và bản đồ van↔xy-lanh đếm trùng.")
            continue
        seen.add((a, b, kind))
        dom = LINK_DOMAIN[kind]
        for nid in (a, b):
            t = (by_id.get(nid) or {}).get("type")
            if dom not in _domains(t):
                bad(f"{(by_id.get(nid) or {}).get('name') or nid} không có cổng "
                    f"{dom} nên không nối kiểu này được",
                    "Chọn loại liên kết khác, hoặc nối tới thiết bị khác",
                    f"Cổng của '{t}' theo GROUPS: "
                    + (", ".join(sorted(_domains(t))) or "không có cổng nào"))
    return problems


def move(root, nid, new_parent_id):
    """Chuyển thiết bị sang cha khác. Trả (ok, vấn đề hoặc None).

    BA ĐIỀU PHẢI CHẶN, và điều thứ ba là chỗ dễ mất dữ liệu nhất:
      · không chuyển được node GỐC (không có cha)
      · cha mới phải hợp lệ theo PARENT_OF — nếu không thì normalize() lại dịch đi
        ngay ở lần dựng sau, và người dùng thấy thao tác của mình 'tự hoàn tác'
      · KHÔNG chuyển vào chính con cháu của nó: nhánh đó sẽ rời khỏi cây và biến
        mất khỏi mọi vòng walk() — mất dữ liệu im lặng, không phải chỉ hiển thị sai
    """
    node = find(root, nid)
    tgt = find(root, new_parent_id)
    if node is None or tgt is None:
        return False, {"rule_code": "T-MOVE-01", "severity": "warn", "node": nid,
                       "what": "không tìm thấy thiết bị hoặc chỗ đến",
                       "field": "parent", "fix": "Chọn lại", "detail": ""}
    if node is root:
        return False, {"rule_code": "T-MOVE-01", "severity": "warn", "node": nid,
                       "what": "không chuyển được gốc cây", "field": "parent",
                       "fix": "Gốc là nguồn khí, luôn ở trên cùng", "detail": ""}
    allowed = PARENT_OF.get(node.get("type"), ((), ""))[0]
    if tgt.get("type") not in allowed:
        return False, {"rule_code": "T-MOVE-01", "severity": "warn", "node": nid,
                       "what": f"{node.get('type')} không lắp vào "
                               f"{tgt.get('type')} được",
                       "field": "parent",
                       "fix": "Chỗ nhận được: "
                              + " · ".join(str(a or "gốc cây") for a in allowed),
                       "detail": PARENT_OF.get(node.get("type"), ((), ""))[1]}
    if any(d is tgt for d, _, _ in walk(node)):
        return False, {"rule_code": "T-MOVE-01", "severity": "warn", "node": nid,
                       "what": "không chuyển vào chính con cháu của nó",
                       "field": "parent",
                       "fix": f"Chuyển '{tgt.get('name') or tgt.get('id')}' ra "
                              f"ngoài trước",
                       "detail": "Làm vậy thì cả nhánh rời khỏi cây và biến mất "
                                 "khỏi BOM mà không báo gì."}
    par = parent_of(root, nid)
    if par is tgt:
        return True, None                    # đã ở đúng chỗ, không phải lỗi
    par["children"] = [c for c in par["children"] if c is not node]
    tgt.setdefault("children", []).append(node)
    return True, None


def inputs_from(root):
    """Mã actuator + số lượng + override — đầu vào cho bom.build().

    Lấy từ cây thay vì bắt người dùng khai riêng: mỗi node cylinder có mã là một
    dòng đầu vào. Loại van khai ở node VAN cha thì truyền xuống.
    """
    out = []
    for n, p, _ in walk(root):
        if n.get("type") != "cylinder" or n.get("manual"):
            continue
        code = (n.get("code") or "").strip()
        if not code:
            continue
        over = dict(n.get("overrides") or {})
        if p and p.get("type") == "valve" and not over.get("valve_function"):
            vf = (p.get("overrides") or {}).get("valve_function")
            if vf:
                over["valve_function"] = vf
        out.append((code, int(n.get("qty") or 1), over))
    return out


def stats(root):
    """Đếm theo trạng thái để UI vẽ vòng tiến độ."""
    spec = typ = emp = 0
    for n, _, _ in walk(root):
        if n.get("type") in ("frl",) and not n.get("code"):
            pass
        if n.get("code"):
            spec += 1
        elif n.get("attrs"):
            typ += 1
        else:
            emp += 1
    return {"specified": spec, "type_only": typ, "empty": emp}


# ── Phụ kiện engine sinh → gắn về đúng node CHA trong cây ────────────────────
#
# Yêu cầu (1): bảng BOM, cây cấu trúc và sơ đồ đều phải thấy quan hệ mẹ–con.
# Dòng BOM mang `for_items` = sinh ra vì actuator nào; ở đây dịch ngược thành
# "phụ kiện này treo dưới node nào".
#
# LOẠI NODE LẤY TỪ DÒNG BOM (`node_type`, do luật khai trong rules.yaml), KHÔNG
# suy từ `layer`. Bảng suy theo layer trước đây chỉ có ba dòng
# (accessory→speed_controller · electrical→sensor · piping→tubing) nên:
#   · van, manifold, gasket, end plate cùng layer 'valve' → không phân biệt được
#   · floating joint, đầu nối, bộ AC KHÔNG có dòng nào → không bao giờ lên sơ đồ
# Đo được: nhập 1 mã xy-lanh ra 8 dòng BOM mà cây chỉ hiện 5 node.


def _hosts_for(root, ctype, line):
    """Node nào được làm CHA của vật tư này? Trả danh sách (node, phần số lượng).

    Ba đường, theo đúng thứ tự ưu tiên:
      1. `for_items` — dòng sinh ra vì actuator nào thì treo dưới chính node đó
         (mỗi xy-lanh thấy phần của mình, không chia đều tổng).
      2. per_system, không có for_items → treo dưới node đầu tiên có loại nằm
         trong PARENT_OF[ctype]. GỐC được ưu tiên vì gốc là nguồn khí: ống và đầu
         nối thuộc MẠNG PHÂN PHỐI của cả máy, không thuộc một xy-lanh nào.
      3. Không có cha hợp lệ nào → trả rỗng, và người gọi BỎ QUA. Không treo bừa:
         cây sai quan hệ thì validate() báo lỗi cho chính vật tư engine tự sinh.
    """
    ok_parents = PARENT_OF.get(ctype, ((), ""))[0]
    items = line.get("for_items") or {}
    if items:
        by_code = {}
        for n, _, _ in walk(root):
            if n.get("code"):
                by_code.setdefault(n["code"], []).append(n)
        per = {}
        for item, q in items.items():
            hits = by_code.get(item, [])
            for h in hits:
                # Cha phải HỢP LỆ: dòng van có for_items là mã xy-lanh, nhưng van
                # KHÔNG phải con của xy-lanh (van là CHA). Không kiểm thì cây sinh
                # ra van treo dưới xy-lanh.
                if h.get("type") not in ok_parents:
                    continue
                cur = per.get(id(h), (h, 0))[1]
                per[id(h)] = (h, cur + q / max(1, len(hits)))
        return list(per.values())
    if root.get("type") in ok_parents:
        return [(root, float(line.get("qty") or 0))]
    for n, _, _ in walk(root):
        if n.get("type") in ok_parents:
            return [(n, float(line.get("qty") or 0))]
    return []


def attach_lines(root, lines):
    """Treo dòng BOM engine sinh vào đúng node cha. Trả số node đã thêm.

    DÒNG CHƯA CÓ MÃ CŨNG ĐƯỢC MỘT NODE. Đây là yêu cầu của bạn: "chưa có mã do
    thiếu dữ liệu đầu vào nhưng phần mềm vẫn phải liệt kê ra ở CẢ sơ đồ và BOM".
    Node đó mang `gap_fields` = còn thiếu gì, để sơ đồ hiện 'CHƯA CÓ MÃ' thay vì
    biến mất — biến mất thì người đọc tưởng máy không cần thứ đó.
    """
    n_new = 0
    # Node đã có một dòng nhận làm "chính nó" — để dòng thứ hai cùng loại không
    # tưởng mình cũng là node đó.
    hosted = set()
    for l in lines:
        if l.get("source") == "manual":
            continue
        ctype = l.get("node_type")
        if not ctype:
            continue
        gap = not l.get("part_number")
        # Node loại này ĐÃ CÓ trong cây và dòng thuộc cả hệ (không for_items) →
        # vật tư đó CHÍNH LÀ node đó, không phải con của nó. Mã do fill_codes()
        # điền; ở đây chỉ đánh dấu khi chưa có mã.
        #
        # CHỈ TÍNH NODE CỦA NGƯỜI DÙNG (không `from_bom`), và mỗi node chỉ nhận
        # MỘT dòng. Không có hai điều kiện đó thì:
        #   · gasket (sinh trước) chiếm chỗ 'manifold_part', và END PLATE — 2 cái
        #     mỗi manifold, BOM thật có SY5000-26-20A ×4 — biến mất khỏi sơ đồ dù
        #     ĐÃ có dòng trong BOM. Đo được đúng lỗi này.
        #   · nhiều dòng cùng loại sẽ cùng trỏ về một node và chỉ hiện một cái.
        if not l.get("for_items"):
            same = [n for n, _, _ in walk(root)
                    if n.get("type") == ctype and not n.get("from_bom")
                    and id(n) not in hosted]
            if same:
                # DÒNG CHƯA CÓ MÃ tìm node CHƯA CÓ MÃ trước. Đo được (yêu cầu 4):
                # ba trạm, van của trạm 3 không sinh được mã → dòng gap 'Van điện
                # từ' chọn node van ĐẦU TIÊN, mà node đó vừa được fill_codes điền
                # mã xong nên không đánh dấu gì, rồi CHIẾM luôn chỗ. Kết quả: BOM
                # nói thiếu một van, còn sơ đồ không chỉ ra van nào.
                h = next((x for x in same if not x.get("code")), same[0]) if gap \
                    else same[0]
                hosted.add(id(h))
                if gap and not h.get("code"):
                    h["gap_item"] = l.get("item")
                    h["gap_fields"] = list(l.get("gap_fields") or [])
                    h["gap_fields_vn"] = list(l.get("gap_fields_vn") or [])
                    h["gap_why"] = l.get("gap_why")
                    h["gap_note"] = l.get("note")
                continue
        label = l.get("part_number") or l.get("item") or ctype
        for h, share in _hosts_for(root, ctype, l):
            kids = h.setdefault("children", [])
            ex = next((c for c in kids if (c.get("code") or c.get("gap_item"))
                       == (l.get("part_number") or l.get("item"))), None)
            if ex:
                ex["qty"] = share
                ex["from_bom"] = True
                continue
            kids.append({
                "id": f"{h['id']}__{label}",
                "type": ctype, "name": label,
                "code": l.get("part_number") or "", "qty": share,
                "attrs": {}, "children": [],
                # đánh dấu để lần dựng sau xoá đi rồi sinh lại — nếu giữ thì số
                # lượng sẽ cộng dồn qua mỗi lần bấm Dựng BOM
                "from_bom": True,
                "rule_code": l.get("rule_code"),
                "confidence": l.get("confidence"),
                **({"gap_item": l.get("item"),
                    "gap_fields": list(l.get("gap_fields") or []),
                    "gap_fields_vn": list(l.get("gap_fields_vn") or []),
                    "gap_why": l.get("gap_why"),
                    "gap_note": l.get("note")} if gap else {}),
            })
            n_new += 1
    return n_new


def drop_generated(root):
    """Xoá phụ kiện do lần dựng trước sinh ra. Giữ node người dùng tự tạo.

    Xoá luôn DẤU 'chưa có mã' trên node của người dùng: dấu đó do lần dựng trước
    đặt, giữ lại thì đã khai đủ dữ liệu rồi mà sơ đồ vẫn báo thiếu.
    """
    for n, _, _ in walk(root):
        for k in ("gap_item", "gap_fields", "gap_fields_vn", "gap_why",
                  "gap_note"):
            n.pop(k, None)
        if n.get("children"):
            n["children"] = [c for c in n["children"] if not c.get("from_bom")]
    return root


def save(con, project_id, root, links=None):
    """Lưu cây + liên kết chéo vào CÙNG một bản ghi.

    Lưu chung vì chúng là một sơ đồ: lưu riêng thì mở lại project cũ có thể ra cây
    mới với liên kết cũ trỏ vào node không còn tồn tại.
    """
    G.ensure_table(con)
    con.execute(
        """insert into project_graph (project_id, graph_json) values (?,?)
           on conflict (project_id) do update set
             graph_json=excluded.graph_json, updated_at=datetime('now')""",
        (project_id, json.dumps({"tree": root, "links": links or []},
                                ensure_ascii=False)))
    con.commit()


def load(con, project_id):
    d = G.load(con, project_id)
    if not d:
        return None
    return d.get("tree") if isinstance(d, dict) and "tree" in d else None


def load_links(con, project_id):
    """Liên kết chéo đã lưu. Trả [] cho project lưu TRƯỚC khi có tính năng này —
    bản ghi cũ không có khoá 'links', và thiếu nó không phải lỗi."""
    d = G.load(con, project_id)
    if not isinstance(d, dict):
        return []
    return d.get("links") or []
