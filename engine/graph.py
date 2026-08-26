"""Đồ thị đấu nối: nodes + edges → đầu vào cho engine BOM.

VÌ SAO CÓ TỆP NÀY (mục 3–5 của prompt-so-do-dau-noi-pneucomplete_2.md): bảng phẳng
không diễn đạt được quan hệ "dùng chung". Đồ thị cấp thêm ba thứ mà bảng phẳng
không có:

  1. VÙNG KHÍ    — các node dùng chung một nguồn cấp (cạnh pneumatic_supply).
                   Luật R-FRL-01 có scope per_system nên LUÔN ra 1 bộ FRL; máy có
                   2 vùng khí thì engine hiện thiếu, không phải thừa.
  2. VAN ↔ XY-LANH — biết chính xác van nào điều khiển xy-lanh nào (cạnh
                   pneumatic_control), thay vì ghép 1-1 theo thứ tự nhập.
  3. NGỮ CẢNH ĐIỆN — điện áp coil lấy từ node PLC nối tới van, thay vì mặc định.

ĐÃ ĐO TRƯỚC KHI VIẾT — hai tiền đề trong tài liệu yêu cầu là SAI:
  · "nhân đôi regulator": không xảy ra. 1/8/20 xy-lanh đều ra đúng 1 dòng FRL.
  · "sai cỡ manifold": không xảy ra. 3/8/12 van → SS5Y5-20-03/-08/-12.
Nên giá trị thật của đồ thị nằm ở ba mục trên, không ở việc chống nhân đôi.

CỔNG (ports): tài liệu nói interfaces.yaml "gần như chính xác" là dữ liệu cổng.
Thực tế có ba khoảng trống, tệp này lấp tường minh trong ports_for():
  · `kind` trong interfaces.yaml = thread/onetouch/rail/tube (kiểu đầu nối VẬT LÝ),
    còn cổng trên canvas cần miền tín hiệu pneumatic/electrical/mechanical. Cùng
    tên, khác nghĩa → tách thành `kind` (miền) và `conn` (đầu nối).
  · `qty: 2` gộp hai cửa thành một mục (7/16 mục như vậy). Canvas BẮT BUỘC tách
    thành 2 cổng có id riêng, vì mục đích của đồ thị là biết van nối cửa A hay B.
  · interfaces.yaml có 0 cổng ĐIỆN. Coil van, tín hiệu cảm biến phải khai ở đây.
"""
import json

from engine import materialize
from engine import problem as PB

# ── Nhóm thiết bị ────────────────────────────────────────────────────────────
# layer phải là một trong LAYER_ORDER của index.html (actuator/valve/air_prep/
# piping/accessory/electrical/other) — nhóm không khớp thì rơi về 'other'.
#
# ports mặc định dùng khi node CHƯA có mã hàng (node "khái niệm", vd van chỉ có
# nhãn "SV1" trong sơ đồ CAD). Khi đã có mã parse được, ports_for() thay bằng cổng
# THẬT đọc từ interfaces.yaml.
# side: cạnh node mà cổng nằm — 'l' trái · 'r' phải · 't' trên · 'b' dưới ·
# 'e' hàng điện tách riêng dưới cùng. Canvas dùng để bố trí VÀ để biết hướng
# thoát của dây khi định tuyến vuông góc (mục 1 + 3 của spec).
# Bố trí lấy theo datasheet, không tự đặt: van 5/2 có 2/A·4/B ở trên, 3/R–1/P–5/S
# ở dưới (P giữa), coil tách hàng riêng.
def P(i, kind, direction, label=None, conn=None, side=None):
    if side is None:
        side = ("e" if kind == "electrical"
                else "l" if direction == "in" else "r")
    return {"id": i, "label": label or i, "kind": kind,
            "direction": direction, "conn": conn, "side": side}

GROUPS = {
    "cylinder": {
        "label": "Xy-lanh / cơ cấu chấp hành", "layer": "actuator",
        "is_actuator": True,
        "ports": [P("A", "pneumatic", "bidirectional"),
                  P("B", "pneumatic", "bidirectional")]},
    "valve": {
        "label": "Van điều khiển", "layer": "valve",
        # Van 5/2 theo ISO 5599-1 / SMC (mục 3 của spec):
        #   trên : 2/A · 4/B      (ra xy-lanh)
        #   dưới : 3/R · 1/P · 5/S (P GIỮA, R/S hai bên)
        #   hàng riêng dưới cùng : 12/coil a · 14/coil b
        # Thứ tự trong danh sách QUYẾT ĐỊNH thứ tự trái→phải trên cạnh đó.
        "ports": [P("2", "pneumatic", "out", "2 / A", side="t"),
                  P("4", "pneumatic", "out", "4 / B", side="t"),
                  P("3", "pneumatic", "out", "3 / R", side="b"),
                  P("1", "pneumatic", "in", "1 / P", side="b"),
                  P("5", "pneumatic", "out", "5 / S", side="b"),
                  P("12", "electrical", "in", "12 / coil a"),
                  P("14", "electrical", "in", "14 / coil b")]},
    "manifold": {
        "label": "Đế manifold", "layer": "valve",
        "ports": [P("P", "pneumatic", "in", "P cấp", side="l"),
                  P("R", "pneumatic", "out", "R xả", side="r"),
                  P("st", "mechanical", "bidirectional", "station", side="t")]},
    "frl": {
        "label": "Bộ xử lý khí F.R.L.", "layer": "air_prep",
        "is_supply": True,
        "ports": [P("IN", "pneumatic", "in"), P("OUT", "pneumatic", "out")]},
    "regulator": {
        "label": "Điều áp", "layer": "air_prep",
        "is_supply": True,
        "ports": [P("IN", "pneumatic", "in"), P("OUT", "pneumatic", "out")]},
    "speed_controller": {
        "label": "Tiết lưu (speed controller)", "layer": "accessory",
        "ports": [P("IN", "pneumatic", "in"), P("OUT", "pneumatic", "out")]},
    "fitting": {
        "label": "Đầu nối", "layer": "piping",
        "ports": [P("1", "pneumatic", "bidirectional"),
                  P("2", "pneumatic", "bidirectional")]},
    "tubing": {
        "label": "Ống", "layer": "piping",
        "ports": [P("1", "pneumatic", "bidirectional"),
                  P("2", "pneumatic", "bidirectional")]},
    "sensor": {
        "label": "Cảm biến", "layer": "electrical",
        "ports": [P("sig", "electrical", "out", "tín hiệu")]},
    # ── BA NHÓM THÊM ĐỂ SƠ ĐỒ LIỆT KÊ ĐỦ VẬT TƯ ─────────────────────────────
    # Không có ba nhóm này thì vật tư engine sinh ra KHÔNG CÓ CHỖ ĐỨNG trên sơ đồ:
    #   · floating joint (JA/JB) — luật R-JOINT-01 sinh, layer 'actuator'
    #   · gasket + end plate     — R-MFD-GASKET-01 / R-MFD-ENDPLATE-01
    #   · giảm âm                — tree.PARENT_OF và tree.EDGE_FOR ĐÃ nhắc tới
    #     'silencer' từ trước, nhưng GROUPS thì không, nên UI không tạo được node
    #     đó và layerOf() trả về 'other'. Đây là thiếu sót, không phải cố ý.
    "joint": {
        "label": "Khớp nối mềm (floating joint)", "layer": "actuator",
        # Mối nối CƠ KHÍ: joint vặn vào ren đầu cần, không phải đường khí. Khai
        # 'pneumatic' ở đây là cho phép nối ống khí vào đầu cần — xem ROLE_DOMAIN.
        "ports": [P("rod", "mechanical", "in", "ren đầu cần", side="l"),
                  P("load", "mechanical", "out", "về tải", side="r")]},
    "manifold_part": {
        "label": "Phụ kiện đế manifold (gasket, end plate)", "layer": "valve",
        "ports": [P("mnt", "mechanical", "bidirectional", "lắp lên đế", side="l")]},
    "silencer": {
        "label": "Giảm âm cửa xả", "layer": "piping",
        "ports": [P("IN", "pneumatic", "in", "từ cửa xả")]},
    "plc": {
        "label": "PLC / bộ điều khiển", "layer": "electrical",
        "ports": [P("out", "electrical", "out", "ngõ ra")]},
    "custom": {
        "label": "Tuỳ chỉnh (ngoài catalog)", "layer": "other",
        "ports": [P("1", "pneumatic", "bidirectional")]},
}

EDGE_KINDS = {
    "pneumatic_control": "van điều khiển xy-lanh",
    "pneumatic_supply": "nguồn khí cấp (dùng để gom vùng khí)",
    "electrical_signal": "tín hiệu điện từ PLC tới van",
    "mechanical_mount": "quan hệ lắp đặt (van gắn lên manifold)",
}

# Suy đoán loại cạnh theo cặp nhóm, để người dùng không phải chọn mỗi lần.
DEFAULT_EDGE_KIND = {
    ("valve", "cylinder"): "pneumatic_control",
    ("manifold", "cylinder"): "pneumatic_control",
    ("frl", "valve"): "pneumatic_supply",
    ("frl", "manifold"): "pneumatic_supply",
    ("regulator", "valve"): "pneumatic_supply",
    ("regulator", "manifold"): "pneumatic_supply",
    ("frl", "regulator"): "pneumatic_supply",
    ("plc", "valve"): "electrical_signal",
    ("valve", "manifold"): "mechanical_mount",
    ("sensor", "plc"): "electrical_signal",
}

# interfaces.yaml `kind` (đầu nối vật lý) → miền tín hiệu dùng cho canvas.
CONN_TO_DOMAIN = {
    "thread": "pneumatic", "onetouch": "pneumatic", "tube": "pneumatic",
    "rail": "mechanical",
}

# `conn` một mình KHÔNG đủ để suy miền: ren đầu cần (rod_end) cũng là `thread`
# nhưng là mối nối CƠ KHÍ, không phải đường khí. Phân loại theo ROLE thắng.
# Xếp sai thì validate cổng sẽ cho phép nối ống khí vào đầu cần xy-lanh.
ROLE_DOMAIN = {
    "rod_end": "mechanical",
    "switch_rail": "mechanical",
    "air_port": "pneumatic", "air_in": "pneumatic", "air_out": "pneumatic",
}

# Hai cửa khí của xy-lanh: đặt tên A/B thay vì air_port_1/2 cho khớp catalog.
AB = ["A", "B"]


def ports_for(con, code, group, templates=None):
    """Cổng THẬT của một mã hàng, đọc từ interfaces.yaml. Rỗng nếu không parse được.

    Tách `qty: n` thành n cổng có id riêng — đây là điểm khác biệt bắt buộc so với
    interfaces.yaml: đồ thị phải biết van nối cửa A hay cửa B, mà một mục
    `qty: 2` thì không phân biệt được.
    """
    if not code:
        return list(GROUPS.get(group, {}).get("ports", []))
    templates = templates if templates is not None else materialize.load_templates()
    m = materialize.materialize(con, code, templates)
    if not m.get("ok") or not m.get("interfaces"):
        return list(GROUPS.get(group, {}).get("ports", []))

    out = []
    for iface in m["interfaces"]:
        role = iface.get("role") or "port"
        conn = iface.get("kind")
        domain = CONN_TO_DOMAIN.get(conn, "pneumatic")
        n = int(iface.get("qty") or 1)
        for k in range(n):
            if role == "air_port" and n == 2:
                pid = AB[k]                      # A / B
            elif n > 1:
                pid = f"{role}_{k + 1}"
            else:
                pid = role
            size = iface.get("size")
            std = iface.get("standard")
            # size đôi khi đã chứa sẵn chuẩn ren ("M10x1.25") — ghép thêm std thành
            # "MM10x1.25". Chỉ ghép khi size chưa bắt đầu bằng std.
            if size and std and not str(size).startswith(str(std)):
                shown = f"{std}{size}"
            else:
                shown = size or ""
            lab = f"{pid} ({shown})" if shown else pid
            kind = ROLE_DOMAIN.get(role, domain)
            # Hai cửa khí xy-lanh: A bên trái, B bên phải — dòng khí đọc từ trái
            # sang phải, nhất quán toàn sơ đồ (mục 3).
            if pid == "A":
                side = "l"
            elif pid == "B":
                side = "r"
            elif role == "air_in":
                side = "l"
            elif role == "air_out":
                side = "r"
            elif kind == "electrical":
                side = "e"
            elif kind == "mechanical":
                side = "t"
            else:
                side = "r"
            out.append({"id": pid, "label": lab, "kind": kind,
                        "direction": "bidirectional", "conn": conn,
                        "side": side, "size": size, "standard": std, "role": role})
    # Cổng ĐIỆN không có trong interfaces.yaml — lấy từ template nhóm.
    have = {p["id"] for p in out}
    for p in GROUPS.get(group, {}).get("ports", []):
        if p["kind"] == "electrical" and p["id"] not in have:
            out.append(dict(p))
    return out


# ── Đọc đồ thị ───────────────────────────────────────────────────────────────

def _by_id(nodes):
    return {n.get("id"): n for n in nodes if n.get("id")}


def supply_zones(nodes, edges):
    """Gom các node dùng chung nguồn cấp — thành phần liên thông qua pneumatic_supply.

    Trả list các set node_id. Đây là thứ bảng phẳng không diễn đạt được: máy có 2
    vùng khí độc lập thì cần 2 bộ xử lý khí, mà luật per_system chỉ ra 1.
    """
    parent = {n["id"]: n["id"] for n in nodes if n.get("id")}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        if e.get("kind") != "pneumatic_supply":
            continue
        a, b = e.get("from"), e.get("to")
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

    groups = {}
    for nid in parent:
        groups.setdefault(find(nid), set()).add(nid)
    # chỉ giữ vùng có ít nhất 1 cạnh supply (node đơn lẻ không phải "vùng khí")
    touched = {x for e in edges if e.get("kind") == "pneumatic_supply"
               for x in (e.get("from"), e.get("to")) if x}
    return [g for g in groups.values() if g & touched]


def control_map(nodes, edges):
    """{node_id xy-lanh: [ (node_id van, cổng van, cổng xy-lanh) ]} từ pneumatic_control."""
    idx = _by_id(nodes)
    out = {}
    for e in edges:
        if e.get("kind") != "pneumatic_control":
            continue
        src, dst = idx.get(e.get("from")), idx.get(e.get("to"))
        if not src or not dst:
            continue
        # cạnh có thể vẽ theo chiều nào cũng được; xác định đầu nào là actuator
        for a, b in ((src, dst), (dst, src)):
            if GROUPS.get(a.get("group"), {}).get("is_actuator"):
                out.setdefault(a["id"], []).append(
                    (b["id"], e.get("from_port"), e.get("to_port")))
                break
    return out


def port_mismatches(nodes, edges):
    """Cạnh nối hai cổng khác MIỀN tín hiệu (điện vào khí) → cảnh báo, không chặn."""
    idx = _by_id(nodes)
    bad = []
    for e in edges:
        a, b = idx.get(e.get("from")), idx.get(e.get("to"))
        if not a or not b:
            bad.append({"edge": e.get("id"), "why": "cạnh trỏ tới node không tồn tại"})
            continue
        pa = next((p for p in (a.get("ports") or []) if p.get("id") == e.get("from_port")), None)
        pb = next((p for p in (b.get("ports") or []) if p.get("id") == e.get("to_port")), None)
        if not pa or not pb:
            continue                    # chưa khai cổng thì không phán
        if pa.get("kind") != pb.get("kind"):
            bad.append({"edge": e.get("id"),
                        "why": f"{a.get('label') or a['id']}.{pa['id']} ({pa['kind']}) "
                               f"nối vào {b.get('label') or b['id']}.{pb['id']} ({pb['kind']})"})
    return bad


def resolve(con, graph, templates=None):
    """Đồ thị → {inputs, config_extra, manual_lines, warnings, info}.

    KHÔNG thay thế rule engine — chỉ chuẩn bị đầu vào cho nó. Đây là "graph
    resolver v0": làm ba việc rẻ mà chắc, và BÁO RÕ những gì chưa làm được thay
    vì im lặng.
    """
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    idx = _by_id(nodes)
    warns, info = [], {}

    # 1. cổng lệch miền tín hiệu
    for m in port_mismatches(nodes, edges):
        warns.append(PB.as_warning(PB.problem(
            "G-PORT-01", "nối sai loại cổng", code="PORT_KIND_MISMATCH",
            field="edge.kind",
            subject=m.get("edge"),
            fix="Xoá dây này rồi nối lại đúng loại cổng",
            how="cổng khí ↔ cổng khí · cổng điện ↔ cổng điện",
            severity="warn", detail=m["why"])))

    # 2. vùng khí
    zones = supply_zones(nodes, edges)
    info["supply_zones"] = len(zones)
    if len(zones) > 1:
        warns.append(PB.as_warning(PB.problem(
            "G-ZONE-01", f"sơ đồ có {len(zones)} vùng khí, engine chỉ sinh 1 bộ xử lý khí",
            code="MULTI_SUPPLY_ZONE",
            field="air_prep", severity="warn",
            fix=f"Thêm tay {len(zones) - 1} bộ xử lý khí vào BOM",
            detail="Luật R-FRL-01 có scope per_system nên chỉ ra 1 bộ. Engine báo "
                   "thiếu thay vì im lặng sinh sai số lượng. Vùng: "
                   + " | ".join(",".join(sorted(z)) for z in zones))))

    # 3. van ↔ xy-lanh
    cmap = control_map(nodes, edges)
    info["controlled"] = {k: [v[0] for v in vs] for k, vs in cmap.items()}

    # 4. điện áp coil từ node PLC
    for e in edges:
        if e.get("kind") != "electrical_signal":
            continue
        for a, b in ((idx.get(e.get("from")), idx.get(e.get("to"))),
                     (idx.get(e.get("to")), idx.get(e.get("from")))):
            if a and b and a.get("group") == "plc":
                v = ((a.get("attrs") or {}).get("voltage")
                     or (a.get("overrides") or {}).get("voltage"))
                if v:
                    info.setdefault("plc_voltage", {})[b["id"]] = v

    # ── dựng inputs cho engine ───────────────────────────────────────────────
    inputs, manual_lines = [], []
    for n in nodes:
        g = GROUPS.get(n.get("group") or "", {})
        code = (n.get("code") or "").strip()
        qty = int(n.get("qty") or 1)
        over = {k: v for k, v in (n.get("overrides") or {}).items()
                if v not in (None, "", "auto")}

        if n.get("manual"):
            # Node tự do: KHÔNG parse, không báo "chưa hiểu mã". Vẫn vào BOM để
            # không sót thiết bị, nhưng đánh dấu rõ là chưa qua kiểm tra kỹ thuật.
            if code or n.get("label"):
                manual_lines.append({
                    "layer": g.get("layer", "other"),
                    "part_number": code or (n.get("label") or "?"),
                    "qty": qty, "unit": "cái",
                    "rule_code": None,
                    "rationale": "Nhập tay, KHÔNG qua kiểm tra kỹ thuật của engine"
                                 + (f" — {n['note']}" if n.get("note") else ""),
                    "confidence": None, "source": "manual"})
            continue

        if not code:
            continue

        if g.get("is_actuator"):
            # Van nối tới xy-lanh mà van có khai loại → truyền xuống xy-lanh.
            # Đây là lợi ích cụ thể của đồ thị: bảng phẳng phải khai ở dòng
            # xy-lanh, còn thực tế người vẽ khai ở van.
            if "valve_function" not in over:
                for vid, _, _ in cmap.get(n["id"], []):
                    vf = ((idx[vid].get("overrides") or {}).get("valve_function")
                          if vid in idx else None)
                    if vf:
                        over["valve_function"] = vf
                        break
            inputs.append((code, qty, over))

    # điện áp: nếu MỌI van nhận cùng một điện áp từ PLC thì đưa vào config
    config_extra = {}
    pv = set((info.get("plc_voltage") or {}).values())
    if len(pv) == 1:
        config_extra["voltage"] = pv.pop()
        info["voltage_from_plc"] = config_extra["voltage"]
    elif len(pv) > 1:
        warns.append(PB.as_warning(PB.problem(
            "G-PLC-01", "các van nhận điện áp khác nhau từ PLC",
            code="MIXED_PLC_VOLTAGE",
            field="voltage", severity="warn",
            fix="Chọn một điện áp ở Cấu hình, hoặc tách thành nhiều lần dựng BOM",
            options=sorted(pv),
            detail="Luật chọn van hiện dùng một giá trị voltage cho cả hệ.")))

    return {"inputs": inputs, "config_extra": config_extra,
            "manual_lines": manual_lines, "warnings": warns, "info": info}


def uncovered_lines(graph, lines, fill):
    """Node trên sơ đồ mà KHÔNG dòng BOM nào đại diện → dòng BOM 'chưa có mã'.

    CHIỀU NGƯỢC của fill_codes, và là nửa còn lại của cùng một yêu cầu: vật tư
    thiếu mã phải hiện ở CẢ sơ đồ và BOM. Đo được chiều này còn im lặng hơn chiều
    kia: người dùng tạo node 'Manifold' trên sơ đồ, không gõ mã, không khai
    `use_manifold` → resolve() gặp `if not code: continue` nên đế manifold KHÔNG
    có trong BOM, mà sơ đồ vẫn vẽ nó. Bảng và sơ đồ nói hai chuyện khác nhau.

    Node được coi là ĐÃ ĐẠI DIỆN khi:
      · có mã (người dùng gõ, hoặc fill_codes vừa điền), hoặc
      · loại node đó đã có một dòng phạm vi CẢ HỆ (dòng không có `for_items`) —
        dòng đó CHÍNH LÀ node này, dù mã còn trống.
    Còn lại thì nói ra, kèm đúng thứ đang thiếu là 'mã hàng'.
    """
    covered = {l["node_type"] for l in lines
               if l.get("node_type") and not l.get("for_items")}
    out = []
    for n in graph.get("nodes") or []:
        if n.get("manual") or (n.get("code") or "").strip() or fill.get(n.get("id")):
            continue
        grp = n.get("group") or ""
        if grp in covered or grp not in GROUPS:
            continue
        g = GROUPS[grp]
        out.append({
            "layer": g.get("layer", "other"), "node_type": grp,
            "part_number": None, "status": "gap",
            "item": f"{g['label']} — {n.get('label') or n.get('id')}",
            "qty": float(n.get("qty") or 1), "unit": "cái",
            "rule_code": None, "confidence": None,
            "gap_fields": ["code"], "gap_fields_vn": ["Mã hàng"],
            "gap_why": "node có trên sơ đồ nhưng chưa có mã",
            "note": "Gõ mã cho node này trên sơ đồ, hoặc bật 'Mã tự do'",
            "rationale": "Node có trên sơ đồ nhưng chưa có mã, và không luật nào "
                         "sinh ra mã cho nó. Liệt kê ở đây để BOM không thiếu vật "
                         "tư mà bảng vẫn trông như đủ.",
        })
    return out


# ── Lưu / đọc đồ thị ─────────────────────────────────────────────────────────

def ensure_table(con):
    con.execute("""
        create table if not exists project_graph (
          project_id integer primary key references project(id) on delete cascade,
          graph_json text not null default '{}' check (json_valid(graph_json)),
          updated_at text not null default (datetime('now')))""")


def save(con, project_id, graph):
    ensure_table(con)
    con.execute(
        """insert into project_graph (project_id, graph_json) values (?,?)
           on conflict (project_id) do update set
             graph_json=excluded.graph_json, updated_at=datetime('now')""",
        (project_id, json.dumps(graph, ensure_ascii=False)))
    con.commit()


def load(con, project_id):
    ensure_table(con)
    r = con.execute("select graph_json from project_graph where project_id=?",
                    (project_id,)).fetchone()
    return json.loads(r["graph_json"]) if r else None


# ── Mục 5 của spec: sau khi dựng BOM, điền mã hàng ngược lại vào sơ đồ ───────

def fill_codes(graph, lines):
    """Trả {node_id: {code, qty, why}} cho các node CHƯA có mã.

    Mục tiêu: sơ đồ sau BOM thành as-built — nhìn sơ đồ biết ngay lắp mã gì,
    không phải tra chéo bảng BOM.

    GHÉP THEO `node_type` CỦA DÒNG, KHÔNG THEO `layer`. Đây là sửa lỗi đo được,
    không phải dọn dẹp: layer 'valve' gộp cả van, manifold, gasket và end plate,
    nên nhánh "tầng này chỉ có một dòng thì gán" đã điền mã VAN SY5220-5MZE-C6 vào
    node MANIFOLD. Sơ đồ hiện MÃ SAI — nặng hơn hiện thiếu, và chính docstring này
    nói "thà để trống hơn điền sai mã vào sơ đồ".
    Dòng không khai node_type (vd xy-lanh do người dùng nhập) thì KHÔNG gán cho ai:
    đoán mã xy-lanh từ xy-lanh khác đúng là thứ phải tránh.

    Gán theo `for_items` (dòng BOM sinh ra vì actuator nào) chứ không theo thứ tự:
      · node van  → dòng phục vụ đúng xy-lanh mà node này điều khiển
      · node khác → nếu loại đó chỉ có DUY NHẤT một dòng thì gán, nhiều hơn thì
        không đoán.
    """
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    idx = _by_id(nodes)
    cmap = control_map(nodes, edges)

    # xy-lanh nào do van nào điều khiển → đảo chiều thành van → [mã xy-lanh]
    valve_serves = {}
    for cyl_id, vs in cmap.items():
        code = (idx.get(cyl_id) or {}).get("code")
        if not code:
            continue
        for vid, _, _ in vs:
            valve_serves.setdefault(vid, set()).add(code)

    by_type = {}
    for l in lines:
        if l.get("source") == "manual" or not l.get("node_type"):
            continue
        # Dòng CHƯA CÓ MÃ không gán vào đây: `code=None` ghi vào node là xoá nhãn
        # chứ không phải thông tin. Việc hiện "chưa có mã" trên sơ đồ do
        # tree.attach_lines() làm, nơi có cả tên vật tư và danh sách thiếu.
        if not l.get("part_number"):
            continue
        by_type.setdefault(l["node_type"], []).append(l)

    out = {}
    for n in nodes:
        if n.get("code") or n.get("manual"):
            continue
        cands = by_type.get(n.get("group") or "") or []
        if not cands:
            continue
        served = valve_serves.get(n["id"])
        if served:
            hit = [l for l in cands
                   if served & set(l.get("for_items") or [])]
            if len(hit) == 1:
                out[n["id"]] = {"code": hit[0]["part_number"], "qty": hit[0]["qty"],
                                "why": f"điều khiển {', '.join(sorted(served))}"}
                continue
        if len(cands) == 1:
            # DÒNG THEO TỪNG ACTUATOR chỉ được gán qua đường `served` ở trên.
            # Đo được: hai node van, van thứ hai điều khiển xy-lanh CHƯA GÕ MÃ →
            # nhánh "loại này chỉ có một dòng" gán mã van của xy-lanh KHÁC cho nó.
            # Cỡ van suy từ lưu lượng của chính xy-lanh đó, nên xy-lanh chưa biết
            # thì cỡ van cũng chưa biết — điền vào là đoán, và đoán im lặng.
            if cands[0].get("for_items"):
                continue
            out[n["id"]] = {"code": cands[0]["part_number"], "qty": cands[0]["qty"],
                            "why": f"dòng duy nhất loại {n.get('group')}"}
    return out
