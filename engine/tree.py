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
    "speed_controller": (("cylinder",),
                         "AS…F air_in ren MALE R1/8 vặn vào air_port xy-lanh "
                         "ren FEMALE Rc1/8 — đo từ interfaces.yaml"),
    "silencer":         (("manifold", "valve"),
                         "BOM thật AN15-02 ×2 cho 11 van → gắn cửa xả CHUNG của "
                         "manifold; chỉ gắn lên van khi van đi rời"),
    "fitting":          (("cylinder", "valve", "manifold", "frl", "regulator", None),
                         "đầu nối vào bất cứ cửa ren nào"),
    "tubing":           (("valve", "manifold", "frl", "cylinder", None),
                         "ống nối giữa các cửa"),
    "sensor":           (("cylinder", None), "cảm biến gắn rãnh xy-lanh"),
    "regulator":        (("frl", "manifold", None), "điều áp trên đường khí"),
    "plc":              ((None,), "PLC đứng riêng, nối bằng tín hiệu điện"),
    "frl":              ((None,), "nguồn khí là gốc cây"),
    "custom":           (("cylinder", "valve", "manifold", "frl", None),
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


def normalize(root):
    """Chuyển node đặt sai về đúng cha. Trả (root, list mô tả đã sửa gì).

    Sửa TƯỜNG MINH và báo ra, không im lặng: người dùng phải biết cây họ nhập đã
    bị dịch chỗ, nếu không họ sẽ tưởng mình khai sai.
    """
    fixed = []

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
            # tìm cha hợp lệ: ưu tiên anh em ngay cạnh, rồi mới lên trên
            cand = None
            for sib in p.get("children") or []:
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
                         f"'{cand.get('name') or cand.get('type')}'")
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


def to_graph(root):
    """Cây → {nodes, edges}. Cạnh suy từ quan hệ cha–con, người dùng không vẽ dây."""
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
    return {"nodes": nodes, "edges": edges}


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
# Layer của dòng → loại node con, và loại node đó có cha hợp lệ là ai (PARENT_OF).
LINE_TO_TYPE = {
    "accessory": "speed_controller",   # AS…F vặn vào cửa xy-lanh
    "electrical": "sensor",            # D-M9 gắn rãnh xy-lanh
    "piping": "tubing",
}


def attach_lines(root, lines):
    """Treo dòng BOM engine sinh vào đúng node cha. Trả số phụ kiện đã gắn.

    Gắn theo `for_items` chứ không theo thứ tự: một mã tiết lưu có thể phục vụ
    nhiều xy-lanh, mà mỗi xy-lanh phải thấy phần của mình.
    """
    by_code = {}
    for n, _, _ in walk(root):
        if n.get("code"):
            by_code.setdefault(n["code"], []).append(n)

    n_new = 0
    for l in lines:
        if l.get("source") == "manual":
            continue
        ctype = LINE_TO_TYPE.get(l.get("layer"))
        if not ctype:
            continue
        # số lượng THEO TỪNG actuator, không chia đều tổng
        per = {}
        for item, q in (l.get("for_items") or {}).items():
            for h in by_code.get(item, []):
                per[id(h)] = (h, per.get(id(h), (h, 0))[1] + q / max(1, len(by_code[item])))
        if not per:
            continue
        for h, share in per.values():
            kids = h.setdefault("children", [])
            ex = next((c for c in kids if c.get("code") == l["part_number"]), None)
            if ex:
                ex["qty"] = share
                ex["from_bom"] = True
                continue
            kids.append({
                "id": f"{h['id']}__{l['part_number']}",
                "type": ctype, "name": l["part_number"],
                "code": l["part_number"], "qty": share,
                "attrs": {}, "children": [],
                # đánh dấu để lần dựng sau xoá đi rồi sinh lại — nếu giữ thì số
                # lượng sẽ cộng dồn qua mỗi lần bấm Dựng BOM
                "from_bom": True,
                "rule_code": l.get("rule_code"),
                "confidence": l.get("confidence"),
            })
            n_new += 1
    return n_new


def drop_generated(root):
    """Xoá phụ kiện do lần dựng trước sinh ra. Giữ node người dùng tự tạo."""
    for n, _, _ in walk(root):
        if n.get("children"):
            n["children"] = [c for c in n["children"] if not c.get("from_bom")]
    return root


def save(con, project_id, root):
    G.ensure_table(con)
    con.execute(
        """insert into project_graph (project_id, graph_json) values (?,?)
           on conflict (project_id) do update set
             graph_json=excluded.graph_json, updated_at=datetime('now')""",
        (project_id, json.dumps({"tree": root}, ensure_ascii=False)))
    con.commit()


def load(con, project_id):
    d = G.load(con, project_id)
    if not d:
        return None
    return d.get("tree") if isinstance(d, dict) and "tree" in d else None
