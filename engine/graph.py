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

# ── Nhóm thiết bị ────────────────────────────────────────────────────────────
# layer phải là một trong LAYER_ORDER của index.html (actuator/valve/air_prep/
# piping/accessory/electrical/other) — nhóm không khớp thì rơi về 'other'.
#
# ports mặc định dùng khi node CHƯA có mã hàng (node "khái niệm", vd van chỉ có
# nhãn "SV1" trong sơ đồ CAD). Khi đã có mã parse được, ports_for() thay bằng cổng
# THẬT đọc từ interfaces.yaml.
P = lambda i, kind, direction, label=None, conn=None: {
    "id": i, "label": label or i, "kind": kind, "direction": direction,
    "conn": conn}

GROUPS = {
    "cylinder": {
        "label": "Xy-lanh / cơ cấu chấp hành", "layer": "actuator",
        "is_actuator": True,
        "ports": [P("A", "pneumatic", "bidirectional"),
                  P("B", "pneumatic", "bidirectional")]},
    "valve": {
        "label": "Van điều khiển", "layer": "valve",
        # Van 5/2: 1=P cấp, 2/4=A/B ra, 3/5=R/S xả, 12/14=coil.
        "ports": [P("1", "pneumatic", "in", "1 / P"),
                  P("2", "pneumatic", "out", "2 / A"),
                  P("4", "pneumatic", "out", "4 / B"),
                  P("3", "pneumatic", "out", "3 / R"),
                  P("5", "pneumatic", "out", "5 / S"),
                  P("12", "electrical", "in", "12 / coil a"),
                  P("14", "electrical", "in", "14 / coil b")]},
    "manifold": {
        "label": "Đế manifold", "layer": "valve",
        "ports": [P("P", "pneumatic", "in", "P cấp"),
                  P("R", "pneumatic", "out", "R xả"),
                  P("st", "mechanical", "bidirectional", "station")]},
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
            out.append({"id": pid, "label": lab,
                        "kind": ROLE_DOMAIN.get(role, domain),
                        "direction": "bidirectional", "conn": conn,
                        "size": size, "standard": std, "role": role})
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
        warns.append({
            "severity": "warn", "code": "PORT_KIND_MISMATCH",
            "rule_code": "G-PORT-01",
            "message": f"Nối sai loại cổng: {m['why']}",
            "rationale": "Cổng điện và cổng khí không nối được với nhau. Engine "
                         "không chặn (có thể bạn đang vẽ nháp) nhưng dòng BOM sinh "
                         "từ cạnh này không đáng tin.",
            "detail": m})

    # 2. vùng khí
    zones = supply_zones(nodes, edges)
    info["supply_zones"] = len(zones)
    if len(zones) > 1:
        warns.append({
            "severity": "warn", "code": "MULTI_SUPPLY_ZONE",
            "rule_code": "G-ZONE-01",
            "message": f"Sơ đồ có {len(zones)} vùng khí độc lập, nhưng luật R-FRL-01 "
                       f"có scope per_system nên engine chỉ sinh 1 bộ xử lý khí. "
                       f"Bạn cần tự thêm {len(zones) - 1} bộ nữa.",
            "rationale": "Đây là hạn chế đã biết của engine, không phải lỗi sơ đồ. "
                         "Engine báo thiếu thay vì im lặng sinh sai số lượng.",
            "detail": {"zones": [sorted(z) for z in zones]}})

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
        warns.append({
            "severity": "warn", "code": "MIXED_PLC_VOLTAGE",
            "rule_code": "G-PLC-01",
            "message": f"Các van nhận điện áp khác nhau từ PLC ({', '.join(sorted(pv))}). "
                       f"Engine chưa sinh van theo từng điện áp — hãy khai riêng.",
            "rationale": "Luật chọn van hiện dùng một giá trị voltage cho cả hệ."})

    return {"inputs": inputs, "config_extra": config_extra,
            "manual_lines": manual_lines, "warnings": warns, "info": info}


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
