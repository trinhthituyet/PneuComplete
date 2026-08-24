"""Engine BOM: nhập actuator → BOM 4 tầng có giải thích, cảnh báo, và GAP.

Quy trình (docs/DESIGN.md §3):
  1 PARSE       mã → series + attrs (engine/parser.py)
  2 EXPAND      fire luật → REQUIREMENT (chưa phải mã hàng)
  3 RESOLVE     requirement → mã hàng, qua generate() hoặc chọn từ part đã có
  4 RANK        khớp interface tuyệt đối > tần suất trong catalog
  5 CONSOLIDATE gộp toàn hệ, cộng số lượng
  6 VALIDATE    kiểm chéo → cảnh báo
  7 EXPLAIN     mỗi dòng mang rule_code + rationale
  8 GAP         requirement không giải được → status='gap', KHÔNG đoán bừa
"""
import json
import math
import os
from collections import defaultdict
from pathlib import Path

from crawler import db
from engine import calc, chart, conf, generate, materialize
from engine import problem as PB
from engine import parser as P

RULES_YAML = db.ROOT / "db" / "seed" / "rules.yaml"

# Số phương án BOM giữ lại trong DB.
#
# VÌ SAO CẦN: mỗi lần dựng BOM ghi một dòng `project` mới và trước đây KHÔNG bao
# giờ xoá. Trên máy phát triển đã lên 35.607 project / 268.531 dòng
# project_output — tổng ~380 nghìn dòng, chiếm gần hết dung lượng DB. Máy người
# dùng cũng phình y như vậy, chỉ chậm hơn.
#
# 200 bản gần nhất: thoải mái để mở lại hay xuất CSV các phương án vừa làm
# (/api/csv?project=N), mà vẫn có chặn trên. Ước lượng ~7,5 dòng output mỗi
# phương án → khoảng 1.500 dòng, không đáng kể.
#
# PNEU_PROJECT_KEEP=0 để tắt hẳn việc dọn (dùng khi cần soi lại lịch sử).
PROJECT_KEEP = int(os.environ.get("PNEU_PROJECT_KEEP") or 200)


def prune_projects(con, keep=None):
    """Xoá phương án cũ, chỉ giữ `keep` bản mới nhất. Trả số phương án đã xoá.

    project_input / project_output / project_warning đều có `on delete cascade`
    nên xoá theo, KHÔNG cần xoá tay từng bảng — nhưng chỉ đúng khi
    `pragma foreign_keys = on`. db.connect() đã bật; nếu ai mở DB bằng
    sqlite3.connect() trần thì cascade không chạy và sẽ để lại dòng mồ côi.
    """
    keep = PROJECT_KEEP if keep is None else keep
    if keep <= 0:
        return 0
    cur = con.execute(
        """delete from project
           where id not in (select id from project order by id desc limit ?)""",
        (keep,))
    return cur.rowcount


DEFAULT_PROJECT = {
    "pressure_mpa": 0.5,
    "cycle_s": 1.5,
    "automation": True,
    "voltage": "24VDC",
    "tube_od_mm": 6.0,
    "tube_color": "BU",
    "tube_roll_length_m": 20,
    "sealant": True,
    "speed_controller_shape": "elbow",
    # ── SỞ THÍCH (§3 của spec cây): nhiều phương án đều lắp được, chọn theo ý
    # người dùng. Khai MỘT LẦN ở mức dự án, không phải từng thiết bị. Đây là nhóm
    # engine có thể HỌC từ BOM cũ, khác hẳn nhóm ràng buộc kỹ thuật.
    #   valve_piping     : cửa van ra ống one-touch (C6/C8…) hay ren (01/02…).
    #                      Phụ thuộc cách đi ống của bạn, không suy được.
    #   fitting_shape    : đầu nối thẳng / vuông (chữ L) / T
    #   exhaust_silencer : có gắn giảm âm ở cửa xả manifold hay không
    "valve_piping": "onetouch",
    "fitting_shape": "elbow",
    "exhaust_silencer": True,
    # Họ speed controller: AS1-E = push-lock (hậu tố A) — đúng loại BOM thật dùng.
    # Đổi sang "AS-E-E" nếu muốn loại núm xoay thường.
    "speed_controller_series": "AS1-E",
    "speed_controller_knob": "push_lock",
    # số speed controller mỗi xy-lanh; None → dùng số cửa khí (2)
    "speed_controller_per_actuator": None,
    # Van: body_ported = van có cửa one-touch riêng (đi ống thẳng tới xy-lanh);
    # base_mounted = cắm lên manifold. BOM thật dùng cả hai kiểu.
    "valve_mounting": "body_ported",
    # LOẠI van theo chức năng cơ cấu. None → engine báo gap, không đoán.
    #   single    kẹp/đẩy một chiều, hồi bằng khí phía kia khi mất điện
    #   double    đi-về, giữ vị trí khi mất điện
    #   3pos_closed / 3pos_exhaust / 3pos_pressure   dừng được ở giữa
    "valve_function": None,
    # Có gá van lên manifold hay đi van rời? Quyết định của bạn — ảnh hưởng
    # gasket, end plate, đế manifold. Dùng được với cả body-ported.
    "use_manifold": None,
    "valve_entry": "m_plug",
    "valve_override": "locking_lever",
    # kiểu manifold quyết định mã end plate; engine KHÔNG suy được
    "manifold_type": None,
    # kiểu đế manifold cho mã SS5Y (20 / 20P / 20SA)
    "manifold_mfd_type": "20",
    "switch_wiring": "2-wire",
    "switch_indicator": "2-color",
    "switch_lead_wire_m": 0.5,
    "safety_factor": 1.5,
    # FRL: cỡ cửa đường trục chính engine KHÔNG suy được (xem R-FRL-01) —
    # để None để engine báo gap thay vì đoán.
    "main_line_port_size": None,
    # thế hệ AC: AC-A-E hoặc AC-D-E — hai catalog khác nhau, mã khác nhau
    "frl_series": "AC-A-E",
    "frl_size": None,            # engine TỰ TÍNH từ đồ thị lưu lượng (xem dưới)
    # ÁP NGUỒN của xưởng — engine KHÔNG suy được, và cần nó để chọn cỡ FRL:
    # đồ thị catalog có hai họ đường theo áp vào (0,7 và 1,0 MPa) cho số khác
    # nhau, mà không điều áp LÊN được nên áp vào phải ≤ áp nguồn.
    "supply_pressure_mpa": None,
    "thread_standard": "Rc",
    "frl_lubricator": False,     # xy-lanh CM2 dùng mỡ sẵn, không cần dầu
    "frl_mist_separator": False, # chỉ cần khi yêu cầu khí sạch cấp cao hơn
    "frl_gauge": "round",
    "frl_auto_drain": "N.O.",
    # chỉ thế hệ -D dùng: E1..E4 khác nhau ở hướng ra dây; V = kèm van VHS
    "frl_gauge_entry": None,
    "frl_gauge_output": None,
    "frl_relief_valve": None,
}


# ── nạp luật ────────────────────────────────────────────────────────────────
def seed_rules(con):
    """Nạp luật từ tệp vào bảng `rule`.

    Bản phát hành đã có luật sẵn trong pneu.db, nên nếu tệp cấu hình không đọc
    được mà DB đã có luật thì im lặng dùng luật trong DB — người dùng cuối không
    cần tệp nguồn. Chỉ báo lỗi khi cả hai đều không có.
    """
    try:
        rules = conf.load(RULES_YAML)
    except conf.ConfigError:
        have = con.execute("select count(*) n from rule").fetchone()["n"]
        if have:
            return have
        raise
    for r in rules:
        con.execute(
            """insert into rule (code, name, scope, priority, when_expr, then_spec,
                                 rationale, source)
               values (?,?,?,?,?,?,?,?)
               on conflict (code) do update set
                 name=excluded.name, scope=excluded.scope, priority=excluded.priority,
                 when_expr=excluded.when_expr, then_spec=excluded.then_spec,
                 rationale=excluded.rationale, source=excluded.source""",
            (r["code"], r["name"], r["scope"], r.get("priority", 100),
             json.dumps(r.get("when", {}), ensure_ascii=False),
             json.dumps(r.get("then", {}), ensure_ascii=False),
             " ".join((r.get("rationale") or "").split()),
             r.get("source")),
        )
    con.commit()
    return len(rules)


def load_rules(con, scope=None):
    q = "select * from rule where enabled=1"
    a = []
    if scope:
        q += " and scope=?"
        a.append(scope)
    q += " order by priority, code"
    out = []
    for r in con.execute(q, a):
        out.append({**dict(r),
                    "when": json.loads(r["when_expr"]),
                    "then": json.loads(r["then_spec"])})
    return out


# ── đánh giá điều kiện ──────────────────────────────────────────────────────
def _cmp(val, op, target):
    # so sánh với null phải làm được: luật cần diễn đạt "ô này CHƯA có giá trị"
    # (ví dụ mã xy-lanh chưa kèm cảm biến thì mới đặt cảm biến riêng)
    if target is None and op in ("eq", "ne"):
        return (val is None) if op == "eq" else (val is not None)
    if val is None:
        return False
    try:
        if op == "eq":
            return val == target
        if op == "ne":
            return val != target
        if op == "gte":
            return float(val) >= float(target)
        if op == "lte":
            return float(val) <= float(target)
        if op == "in":
            return val in target
    except (TypeError, ValueError):
        return False
    return False


def matches(when, ctx):
    for cond in (when or {}).get("all", []):
        attr = cond["attr"]
        op = next((k for k in ("eq", "ne", "gte", "lte", "in") if k in cond), None)
        if op is None or not _cmp(ctx.get(attr), op, cond[op]):
            return False
    return True


def _subst(spec, ctx, project):
    """Thay {from_ctx: k} / {from_project: k} bằng giá trị thật."""
    if isinstance(spec, dict):
        if "from_ctx" in spec:
            return ctx.get(spec["from_ctx"])
        if "from_project" in spec:
            return project.get(spec["from_project"])
        return {k: _subst(v, ctx, project) for k, v in spec.items()}
    if isinstance(spec, list):
        return [_subst(v, ctx, project) for v in spec]
    return spec


# ── resolve ─────────────────────────────────────────────────────────────────
def _options_for(con, field, project):
    """Các lựa chọn hợp lệ cho một field còn thiếu.

    Có nhiều lựa chọn thì PHẢI liệt kê ra (yêu cầu của prompt báo lỗi) — bắt người
    dùng tự mở catalog tra là đúng cái phần mềm này ra đời để tránh.
    """
    if field == "valve_function":
        return list(VALVE_FUNCTION)
    if field == "valve_series_size":
        return chart.valve_sizes() or ["SY3000", "SY5000", "SY7000"]
    if field == "manifold_type":
        return ["20, 23, 20SA, 23SA", "20P, 23P"]
    if field in ("main_line_port_size", "frl_size"):
        # đọc thẳng từ ngữ pháp họ FRL đang chọn — không hard-code
        slot = "port_size" if field == "main_line_port_size" else "size"
        cid = project.get("frl_series") or "AC-D-E"
        rows = con.execute(
            """select o.code, o.label from code_option o
               join code_slot cs on cs.id = o.slot_id
               join series s on s.id = cs.series_id
               where s.catalog_id = ? and cs.name = ? order by o.code""",
            (cid, slot)).fetchall()
        return [r["label"] or r["code"] for r in rows] or None
    if field == "tube_color":
        rows = con.execute(
            """select o.code from code_option o join code_slot cs on cs.id=o.slot_id
               join series s on s.id=cs.series_id
               where s.catalog_id='TU-E' and cs.name='color' order by o.code""").fetchall()
        return [r["code"] for r in rows][:10] or None
    return None


def _resolve_need(con, need, ctx, project, src_part_id, templates):
    """REQUIREMENT → dòng BOM cụ thể, hoặc gap kèm lý do."""
    # luật có thể khai thông tin BẮT BUỘC người dùng cấp. Không có thì gap —
    # tuyệt đối không lấy giá trị mặc định do engine tự nghĩ ra (A3-5).
    ri = need.get("requires_input")
    if ri and project.get(ri) in (None, ""):
        # 3 phần ngắn (Prompt sửa cách báo lỗi): sai ở đâu · sửa gì · sửa thế nào.
        # rationale dài của luật KHÔNG vào đây, nó đi vào detail.
        return {"gap": f"thiếu {PB.field_vn(ri)}", "field": ri,
                "options": _options_for(con, ri, project)}
    want = {k: v for k, v in (_subst(need.get("want", {}), ctx, project) or {}).items()
            if v is not None}
    qty = _subst(need.get("qty", 1), ctx, project)
    if qty in (None, ""):
        qty = _subst(need.get("qty_default", 1), ctx, project) or 1
    qty = float(qty)

    # (a) chọn từ mã thật đã có trong bảng part (dùng khi chưa giải mã được ngữ pháp)
    if need.get("from_parts"):
        sid = con.execute("select id from series where catalog_id=?",
                          (need["from_parts"],)).fetchone()
        if not sid:
            return {"gap": f"chưa có dữ liệu họ {need['from_parts']}"}
        rows = con.execute("select * from part where series_id=?", (sid["id"],)).fetchall()
        cands = []
        for r in rows:
            a = json.loads(r["attrs"] or "{}")
            if all(str(a.get(k)) == str(v) for k, v in want.items()):
                cands.append((a.get(need.get("rank_by", ""), 0) or 0, r, a))
        if not cands:
            return {"gap": f"không mã nào trong họ {need['from_parts']} thoả yêu cầu",
                    "detail": f"điều kiện: {want}"}
        cands.sort(key=lambda x: -x[0])
        best = cands[0]
        a = best[2]
        if a.get("occurrences_in_catalog"):
            note = (f"chọn theo tần suất trong catalog "
                    f"({a['occurrences_in_catalog']} lần); mã chưa giải mã hết")
            conf = 0.6
        else:
            note = f"tra bảng: {a.get('_source', 'catalog')}"
            conf = 0.85 if len(cands) == 1 else 0.7
        return {"part_number": best[1]["part_number"], "qty": qty,
                "attrs": a, "confidence": conf,
                "alternatives": [c[1]["part_number"] for c in cands[1:4]],
                "note": note}

    # (b) sinh mã từ ngữ pháp. from_series có thể là {from_project: ...}
    from_series = _subst(need["from_series"], ctx, project)
    sid = con.execute("select id from series where catalog_id=?",
                      (from_series,)).fetchone()
    if not sid:
        return {"gap": f"không có series {from_series}"}
    g = generate.generate(con, sid["id"], want,
                          soft=tuple(need.get("want_soft") or ()))
    if not g.get("ok"):
        if g.get("error"):
            return {"gap": f"{from_series}: {g['error']}"}
        bits = "; ".join(f"{u['slot']} ({u['reason']})" for u in g["undecided"])
        # nếu ràng buộc lấy từ ctx mà ctx không có giá trị → nói rõ THIẾU DỮ LIỆU
        empty = [k for k, v in (need.get("want") or {}).items()
                 if isinstance(v, dict) and "from_ctx" in v
                 and ctx.get(v["from_ctx"]) in (None, "")]
        if empty:
            return {"gap": f"{from_series}: thiếu dữ liệu {', '.join(empty)} của series "
                           f"nguồn — chưa trích được từ catalog, nên không chọn được mã"}
        return {"gap": f"{from_series}: chưa quyết được ô {bits}"}

    m = materialize.materialize(con, g["part_number"], templates)
    if not m["ok"]:
        return {"gap": f"{g['part_number']}: {m['error']}"}

    # (c) kiểm ghép interface với item nguồn nếu luật yêu cầu
    conf, note = 0.9, None
    if need.get("mate") and src_part_id:
        role = need["mate"]["role"]
        tgt = con.execute(
            "select * from part_interface where part_id=? and role=?",
            (src_part_id, role)).fetchone()
        if tgt is None:
            return {"gap": f"item nguồn không có giao diện '{role}'"}
        ok_any, why = False, []
        for cand in con.execute("select * from part_interface where part_id=?",
                                (m["part_id"],)):
            ok, w = materialize.mates(con, cand, tgt)
            why.append(f"{cand['role']}: {w}")
            if ok:
                ok_any = True
                note = w
                break
        if not ok_any:
            return {"gap": f"{g['part_number']} không ghép được vào '{role}': "
                           f"{'; '.join(why[:2])}"}
        conf = 0.95

    if g.get("relaxed"):
        bits = "; ".join(f"{r['slot']} (bỏ yêu cầu {', '.join(r['dropped'])})"
                         for r in g["relaxed"])
        note = ((note + " · ") if note else "") + f"catalog không có lựa chọn: {bits}"
    cap = need.get("confidence_cap")
    if cap:
        conf = min(conf, float(cap))
    return {"part_number": g["part_number"], "qty": qty, "attrs": m["attrs"],
            "confidence": conf, "note": note, "part_id": m["part_id"]}


def _count_bad_threads(con, lines):
    """Đếm cặp ren male/female THẬT SỰ không lắp được trong BOM.

    Bản trước đếm số chuẩn ren khác nhau — sai, vì R male vào Rc female là đúng và
    cố ý (ISO 7/JIS). BOM đúng vẫn có Rc + R + M nên luật cũ luôn báo lỗi giả.
    Chỉ xét role thuộc đường khí; ren đầu cần (rod_end) không phải mối nối khí.
    """
    AIR = ("air_port", "air_in", "air_out", "air_supply", "exhaust")
    pns = tuple({l["part_number"] for l in lines})
    if not pns:
        return 0
    rows = con.execute(
        """select pi.* from part_interface pi join part p on p.id = pi.part_id
           where pi.kind='thread' and p.part_number in ({})""".format(
            ",".join("?" * len(pns))), pns).fetchall()
    males = [r for r in rows if r["gender"] == "male" and r["role"] in AIR]
    females = [r for r in rows if r["gender"] == "female" and r["role"] in AIR]
    bad = 0
    for m in males:
        for f in females:
            if (m["size"] or "") != (f["size"] or ""):
                continue                      # khác cỡ thì không phải cặp định lắp
            ok, _ = materialize.mates(con, m, f)
            if not ok:
                bad += 1
    return bad


# ── orchestrator ────────────────────────────────────────────────────────────
VALVE_FUNCTION = {
    "single":        {"positions": 2, "solenoid": "single", "center": None},
    "double":        {"positions": 2, "solenoid": "double", "center": None},
    "3pos_closed":   {"positions": 3, "solenoid": None, "center": "closed"},
    "3pos_exhaust":  {"positions": 3, "solenoid": None, "center": "exhaust"},
    "3pos_pressure": {"positions": 3, "solenoid": None, "center": "pressure"},
}


def _expand_valve_function(cfg):
    """valve_function → valve_positions / valve_solenoid / valve_center."""
    f = cfg.get("valve_function")
    m = VALVE_FUNCTION.get(f)
    if not m:
        return cfg
    return {**cfg, "valve_positions": m["positions"],
            "valve_solenoid": m["solenoid"], "valve_center": m["center"]}


def build(con, inputs, project=None, project_name="demo"):
    """inputs: [(mã, số_lượng)] hoặc [(mã, số_lượng, {override})].

    Override theo TỪNG actuator cần thiết vì loại van phụ thuộc CHỨC NĂNG của cơ
    cấu, không phải loại xy-lanh: cơ cấu kẹp dùng van 5/2 single, cơ cấu đi-về có
    dừng giữa dùng 3-position. Golden test trên máy 23-432 cho thấy một máy dùng
    đồng thời SY5120 (single) ×5, SY5220 (double) ×2, SY5420 (3-pos exhaust) ×4 —
    luật chung "mỗi xy-lanh một van 5/2 double" sai với thực tế.
    """
    project = {**DEFAULT_PROJECT, **(project or {})}
    templates = materialize.load_templates()
    materialize.seed_thread_compat(con)

    cur = con.execute("insert into project (name, config) values (?,?)",
                      (project_name, json.dumps(project, ensure_ascii=False)))
    pid = cur.lastrowid
    prune_projects(con)

    lines, warns, gaps, calcs = [], [], [], []
    per_act = load_rules(con, "per_actuator")
    onetouch_open = 0
    # Đếm đầu one-touch THEO TỪNG ĐƯỜNG KÍNH. Máy thật dùng nhiều cỡ ống cùng lúc
    # (BOM 23-432: TU0604B-200 cho nhánh xy-lanh + TU1065B-100 cho trục chính),
    # gộp thành một số thì engine chỉ đề xuất được một loại ống.
    onetouch_by_od = defaultdict(float)

    # ── LƯỢT TÍNH TRƯỚC: engine tự quyết thay vì hỏi (mục 6 của spec) ────────
    #
    # Cỡ van phụ thuộc TỔNG lưu lượng, mà tổng chỉ biết sau khi duyệt hết actuator
    # — trong khi luật R-VLV-01 có scope per_actuator nên chạy TRONG lượt duyệt.
    # Vì vậy phải tính lưu lượng một lượt trước rồi mới chọn cỡ van.
    #
    # Nguyên tắc: chỉ điền khi người dùng CHƯA khai. Suy luận không bao giờ ghi đè
    # điều bạn khai tay.
    auto = {}
    # Tổng lưu lượng tính MỘT LẦN, dùng cho cả cỡ van và cỡ FRL. Trước đây nó
    # nằm trong nhánh `if not valve_series_size` nên khi người dùng đã khai cỡ
    # van thì cỡ FRL không còn số liệu để tính.
    need_lpm = 0.0
    for it in inputs:
        mm = materialize.materialize(con, it[0], templates)
        if not mm.get("ok"):
            continue
        aa = mm.get("attrs") or {}
        cc = calc.summary(aa.get("bore_mm"), aa.get("stroke_mm"),
                          project["pressure_mpa"], project["cycle_s"], it[1],
                          safety=project["safety_factor"], rod_mm=aa.get("rod_dia_mm"))
        need_lpm += cc.get("required_flow_lpm") or 0.0

    if not project.get("valve_series_size"):
        size, why = chart.pick_valve_size(need_lpm, project["pressure_mpa"])
        if size:
            project["valve_series_size"] = size
            auto["valve_series_size"] = (size, why)
        else:
            auto["_valve_size_failed"] = why

    # Cỡ FRL: trước đây bắt người dùng khai vì "catalog chỉ in dạng ĐỒ THỊ".
    # Đã số hoá (db/seed/charts/ac-flow.yaml, qua cổng tests/test_chart.py) nên
    # engine tự tra. Thiếu áp nguồn thì pick_frl_size trả gap nói rõ, không đoán.
    if not project.get("frl_size"):
        fam = (project.get("frl_series") or "AC-A-E").split("-")[0]
        size, why = chart.pick_frl_size(
            need_lpm, project["pressure_mpa"],
            project.get("supply_pressure_mpa"), fam,
            # Phụ kiện nối SAU bộ điều áp làm sụt thêm áp trước khi khí tới máy —
            # phải cộng vào yêu cầu, không được bỏ qua.
            lubricator=bool(project.get("frl_lubricator")),
            mist_separator=bool(project.get("frl_mist_separator")))
        if size:
            project["frl_size"] = size
            auto["frl_size"] = (size, why)
        else:
            auto["_frl_size_failed"] = why
    elif project.get("supply_pressure_mpa"):
        # Người dùng ĐÃ chốt cỡ — không ghi đè, nhưng vẫn KIỂM được bằng đồ thị.
        # Trước đây engine chỉ nói "chưa kiểm được lưu lượng, bạn tự mở catalog";
        # giờ có số nên kiểm luôn: chọn thiếu cỡ là sụt áp khi nhiều xy-lanh chạy.
        need_size, why = chart.pick_frl_size(
            need_lpm, project["pressure_mpa"], project["supply_pressure_mpa"],
            (project.get("frl_series") or "AC-A-E").split("-")[0],
            lubricator=bool(project.get("frl_lubricator")),
            mist_separator=bool(project.get("frl_mist_separator")))
        auto["frl_size_checked"] = (need_size, why)
        try:
            too_small = need_size and int(need_size) > int(project["frl_size"])
        except (TypeError, ValueError):
            too_small = False
        if too_small:
            auto["_frl_too_small"] = (project["frl_size"], need_size, why)

    for item in inputs:
        code, count = item[0], item[1]
        over = item[2] if len(item) > 2 else {}
        con.execute("""insert into project_input (project_id, raw_code, qty, overrides)
                       values (?,?,?,?)""",
                    (pid, code, count, json.dumps(over, ensure_ascii=False)))
        m = materialize.materialize(con, code, templates)
        if not m["ok"]:
            gaps.append(PB.as_gap(PB.problem(
                "R-PARSE-00", "không đọc được mã hàng", field="code",
                subject=code,
                fix=f"Sửa mã {code}, hoặc bật 'Mã tự do' cho node này",
                detail=m["error"])))
            continue

        # Loại van suy theo TỪNG CƠ CẤU — phải đặt SAU materialize() vì cần attrs:
        # xy-lanh tác động đơn → van 3/2, tác động kép → van 5/2. Chỉ đề xuất khi
        # bạn chưa khai; bạn override thì thắng.
        merged_over = dict(over)
        if not merged_over.get("valve_function") and not project.get("valve_function"):
            acting = (m.get("attrs") or {}).get("acting")
            merged_over["valve_function"] = "single" if acting == "single" else "double"
            auto.setdefault("valve_function", {})[code] = merged_over["valve_function"]
            # HẠ TIN CẬY của dòng van khi loại van là do engine SUY, không do bạn khai.
            # Đo được trên máy 23-432: engine suy ra 17 van `double`, thực tế là
            # 5 single + 2 double + 4 3-pos. Một cảnh báo chung không sửa được số
            # lượng sai — phải hiện ngay trên từng dòng để người ký BOM thấy.
            vf_guessed = True
        else:
            vf_guessed = False
        item_project = _expand_valve_function({**project, **merged_over})

        a = m["attrs"]
        ports = con.execute(
            "select qty from part_interface where part_id=? and role='air_port'",
            (m["part_id"],)).fetchone()
        # đường kính cần lấy từ attrs của mã (do pdf_dim_table ghi vào option bore),
        # KHÔNG từ bảng hardcode — xem ghi chú A3-1 trong engine/calc.py
        c = calc.summary(a.get("bore_mm"), a.get("stroke_mm"),
                         project["pressure_mpa"], project["cycle_s"], count,
                         project["safety_factor"],
                         rod_mm=a.get("rod_dia_mm")) if a.get("bore_mm") else {}
        calcs.append({"item": code, "count": count, **c})

        port_iface = con.execute(
            "select * from part_interface where part_id=? and role='air_port'",
            (m["part_id"],)).fetchone()
        ctx = {
            **a,
            "acting": "double",          # CM2 tác động 2 chiều (bảng variation HTML)
            "automation": project["automation"],
            "port_count": ports["qty"] if ports else 2,
            "port_size": port_iface["size"] if port_iface else None,
            "tube_od_mm": project["tube_od_mm"],
            "piston_speed_mm_s": c.get("piston_speed_mm_s"),
            "rod_end_thread": a.get("rod_end_thread"),
            "rod_end_male_thread": a.get("rod_end_male_thread"),
            "rod_end": a.get("rod_end"),
            # Ren đầu cần HIỆU DỤNG — chỉ có giá trị khi đầu cần là REN NGOÀI,
            # vì floating joint cần ren ngoài để vặn vào. Hai họ khai khác nhau:
            #   CM2  : sơ đồ ghi 'Nil = Male rod end' → mặc định ĐÃ là ren ngoài,
            #          cỡ ren nằm ở attrs.rod_end_thread (cột MM bảng kích thước)
            #   CQS  : phải chọn option M mới có ren ngoài, cỡ ở rod_end_male_thread
            # MGP là guide cylinder — đầu ra là tấm dẫn hướng, không có cần ren.
            "rod_end_thread_male": (
                a.get("rod_end_male_thread") if a.get("rod_end") == "male"
                else (a.get("rod_end_thread") if a.get("rod_end") is None else None)),
            "has_guide": bool(a.get("bearing")),
        }
        lines.append({"layer": "actuator", "part_number": m["part_number"],
                      "qty": count, "rule_code": None,
                      "rationale": "do người dùng nhập", "confidence": 1.0})

        for r in per_act:
            if not matches(r["when"], ctx):
                continue
            if "warn" in r["then"]:
                w = _subst(r["then"]["warn"], ctx, item_project)
                warns.append({**w, "rule_code": r["code"], "item": code,
                              "rationale": r["rationale"]})
                continue
            need = r["then"].get("need")
            if not need:
                continue
            res = _resolve_need(con, need, ctx, item_project, m["part_id"], templates)
            if "gap" in res:
                gaps.append(PB.as_gap(PB.problem(
                    r["code"], res["gap"], subject=code,
                    field=res.get("field"), options=res.get("options"),
                    detail=f"{res.get('detail') or ''} {r['rationale'] or ''}".strip())))
                continue
            conf_line = res["confidence"]
            if vf_guessed and need.get("layer") == "valve" and conf_line:
                conf_line = min(conf_line, 0.5)
            lines.append({"layer": need["layer"], "part_number": res["part_number"],
                          "qty": res["qty"] * count, "rule_code": r["code"],
                          "rationale": r["rationale"], "confidence": conf_line,
                          "note": res.get("note"),
                          # for_items: {mã actuator: số lượng dòng này sinh CHO nó}.
                          # Phải là TỪ ĐIỂN chứ không phải danh sách: dòng BOM đã
                          # gộp theo mã, nên nếu chỉ giữ danh sách thì lúc treo phụ
                          # kiện về từng xy-lanh phải chia đều — sai. Ví dụ 2 con
                          # CDM2 + 1 con MGPM dùng chung mã tiết lưu: tổng 6 cái,
                          # chia đều ra 3/3 trong khi thực tế là 4/2.
                          "for_items": {code: res["qty"] * count},
                          "alternatives": res.get("alternatives")})
            # Đếm đầu one-touch còn hở bằng cách xem GIAO DIỆN THẬT của mã vừa
            # chọn, không so tên series. Bản trước hardcode `== "AS-E-E"` nên khi
            # đổi sang họ push-lock thì đếm ra 0 và dòng ống biến mất âm thầm.
            if res.get("part_id"):
                for r_ot in con.execute(
                        """select tube_od_mm od, coalesce(sum(qty),0) n
                           from part_interface where part_id=? and kind='onetouch'
                           group by tube_od_mm""", (res["part_id"],)):
                    if r_ot["od"]:
                        onetouch_by_od[float(r_ot["od"])] += \
                            r_ot["n"] * res["qty"] * count
                        onetouch_open += r_ot["n"] * res["qty"] * count

    # ── NÓI RA những gì engine tự quyết ─────────────────────────────────────
    # Tự quyết mà im lặng thì người dùng không biết có gì cần kiểm lại. Dùng
    # severity='info' để phân biệt với cảnh báo kỹ thuật thật.
    if auto.get("valve_series_size"):
        size, why = auto["valve_series_size"]
        warns.append({"severity": "info", "code": "AUTO_VALVE_SIZE",
                      "rule_code": "R-VLV-02",
                      "message": f"Cỡ van: {size} (engine tự tính từ lưu lượng)",
                      "rationale": why, "detail": why})
    if auto.get("_valve_size_failed"):
        gaps.append(PB.as_gap(PB.problem(
            "R-VLV-02", "chưa chọn được cỡ van từ lưu lượng",
            field="valve_series_size", options=chart.valve_sizes() or None,
            detail=auto["_valve_size_failed"])))
    if auto.get("frl_size"):
        size, why = auto["frl_size"]
        # THẾ HỆ CATALOG có khớp không? DB có ngữ pháp cả AC-A và AC-D, nhưng
        # DOCUMENT/ chỉ có đồ thị lưu lượng của -D cho cỡ 20–60. Dùng đường -D để
        # chọn linh kiện -A là giả thiết CHƯA KIỂM ĐƯỢC — nâng lên 'warning' và
        # nói rõ, chứ không báo 'info' như thể đã chắc.
        fam_parts = (project.get("frl_series") or "").split("-")
        gen_proj = fam_parts[1] if len(fam_parts) > 2 else None
        gen_chart = chart.frl_chart_generation(fam_parts[0] or "AC")
        mismatch = gen_proj and gen_chart and gen_proj != gen_chart
        if mismatch:
            why += (f" ⚠ Đồ thị số hoá là catalog thế hệ -{gen_chart}, còn mã đang "
                    f"sinh là thế hệ -{gen_proj}. DOCUMENT/ không có đồ thị lưu "
                    f"lượng -{gen_proj} cho cỡ 20–60 (bản -A duy nhất là "
                    f"ES40-60-AC10-A.pdf, chỉ AC10) nên chưa đối chiếu được. "
                    f"Cần xác nhận, hoặc đổi frl_series sang AC-{gen_chart}-E.")
        # từ vựng severity của project_output là ('info','warn','error')
        warns.append({"severity": "warn" if mismatch else "info",
                      "code": "AUTO_FRL_SIZE_OTHER_GEN" if mismatch
                              else "AUTO_FRL_SIZE",
                      "rule_code": "R-FRL-02",
                      "message": f"Cỡ AC: {size} (engine tra đồ thị lưu lượng"
                                 + (f", đồ thị -{gen_chart} ≠ mã -{gen_proj})"
                                    if mismatch else ")"),
                      "rationale": why, "detail": why})
    if auto.get("_frl_size_failed"):
        # Thiếu áp nguồn là NGUYÊN NHÂN thường gặp nhất, và nó là thứ người dùng
        # biết ngay — nên hỏi đúng trường đó thay vì bắt tra catalog chọn cỡ AC.
        need_supply = not project.get("supply_pressure_mpa")
        gaps.append(PB.as_gap(PB.problem(
            "R-FRL-02",
            "chưa chọn được cỡ AC từ lưu lượng",
            field="supply_pressure_mpa" if need_supply else "frl_size",
            fix=("Khai áp nguồn của xưởng (MPa) — engine sẽ tự tra đồ thị"
                 if need_supply else "Chốt cỡ AC ở cấu hình"),
            detail=auto["_frl_size_failed"])))
    if auto.get("_frl_too_small"):
        got, need, why = auto["_frl_too_small"]
        warns.append({"severity": "warn", "code": "FRL_SIZE_TOO_SMALL",
                      "rule_code": "R-FRL-02",
                      "message": f"Cỡ AC {got} bạn khai KHÔNG đủ lưu lượng — "
                                 f"đồ thị cho thấy cần cỡ {need}",
                      "rationale": why, "detail": why})
    if auto.get("valve_function"):
        vf = auto["valve_function"]
        warns.append({"severity": "info", "code": "AUTO_VALVE_FUNCTION",
                      "rule_code": "R-VLV-01",
                      "message": "Loại van: "
                                 + ", ".join(f"{k} → {v}" for k, v in vf.items()),
                      "rationale": "Tác động kép → 5/2 (double), tác động đơn → 3/2 "
                                   "(single). Cần dừng giữa hành trình thì đổi sang "
                                   "3pos_closed / 3pos_exhaust / 3pos_pressure ở node.",
                      "detail": vf})

    # ── CONSOLIDATE toàn hệ ─────────────────────────────────────────────────
    roll = project["tube_roll_length_m"]
    # KHÔNG ước lượng chiều dài ống (A3-5). Chỉ tính khi người dùng đã khai tổng mét.
    total_m = project.get("tube_total_m")
    rolls = math.ceil(total_m / roll) if total_m else None
    sys_ctx = {
        "actuator_count": sum(i[1] for i in inputs),
        "valve_count": sum(l["qty"] for l in lines if l["layer"] == "valve"),
        "valve_mounting": project.get("valve_mounting"),
        "use_manifold": project.get("use_manifold"),
        "open_onetouch_count": onetouch_open,
        "tube_rolls_needed": rolls,
        "required_flow_lpm": round(sum(c.get("required_flow_lpm", 0) for c in calcs), 1),
        "total_flow_lpm": round(sum(c.get("total_flow_lpm", 0) for c in calcs), 1),
        "incompatible_thread_pairs": _count_bad_threads(con, lines),
        "max_actuator_port_size": next(
            (r["size"] for r in con.execute(
                """select pi.size from part_interface pi join part p on p.id=pi.part_id
                   where pi.role='air_port' order by pi.size desc limit 1""")), None),
    }
    for r in load_rules(con, "per_system"):
        if not matches(r["when"], sys_ctx):
            continue
        if "warn" in r["then"]:
            w = _subst(r["then"]["warn"], sys_ctx, project)
            warns.append({**w, "rule_code": r["code"], "rationale": r["rationale"]})
            continue
        if "gap" in r["then"]:
            g = r["then"]["gap"]
            gaps.append(PB.as_gap(PB.problem(
                r["code"], g["what"], field=g.get("field"),
                options=g.get("options"),
                detail=f"{' '.join((g.get('reason') or '').split())} "
                       f"{r['rationale'] or ''}".strip())))
            continue
        need = r["then"].get("need")
        if not need:
            continue

        # Luật khai `per_tube_od` chạy MỘT LẦN cho mỗi đường kính ống trong hệ.
        variants = [None]
        if need.get("per_tube_od"):
            variants = sorted(onetouch_by_od) or [project.get("tube_od_mm")]

        for od in variants:
            ctx_v = dict(sys_ctx)
            proj_v = dict(project)
            if od:
                proj_v["tube_od_mm"] = od
                n_ends = onetouch_by_od.get(od, 0)
                share = (n_ends / onetouch_open) if onetouch_open else 1.0
                m_v = (project.get("tube_total_m") or 0) * share
                roll = project["tube_roll_length_m"]
                ctx_v["tube_rolls_needed"] = max(1, math.ceil(m_v / roll)) if m_v else None
                ctx_v["tube_od_mm"] = od
            res = _resolve_need(con, need, ctx_v, proj_v, None, templates)
            if "gap" in res:
                gaps.append(PB.as_gap(PB.problem(
                    r["code"], res["gap"], field=res.get("field"),
                    options=res.get("options"),
                    detail=f"{res.get('detail') or ''} {r['rationale'] or ''}".strip())))
                continue
            note = res.get("note")
            if od:
                note = ((note + " · ") if note else "") + \
                    f"ø{od}: {int(onetouch_by_od.get(od,0))} đầu one-touch trong hệ"
            lines.append({"layer": need["layer"], "part_number": res["part_number"],
                          "qty": res["qty"], "rule_code": r["code"],
                          "rationale": r["rationale"], "confidence": res["confidence"],
                          "note": note, "unit": need.get("unit")})

    # cảnh báo phụ thuộc kết quả (FRL có được đề xuất không) → chạy sau
    sys_ctx["frl_proposed"] = any(l["layer"] == "air_prep" for l in lines)
    # Đã KIỂM được lưu lượng FRL bằng đồ thị chưa — dù engine tự chọn cỡ hay chỉ
    # kiểm lại cỡ người dùng khai. V-FRL-FLOW-01 chỉ được cảnh báo khi CHƯA kiểm;
    # đồ thị đã số hoá rồi mà vẫn nói "engine không kiểm được, bạn tự mở PDF
    # trang 10" là nói sai với người dùng.
    sys_ctx["frl_flow_checked"] = bool(auto.get("frl_size")
                                       or auto.get("frl_size_checked"))
    for r in load_rules(con, "per_system"):
        if "warn" not in r["then"] or r["code"] in {w.get("rule_code") for w in warns}:
            continue
        if matches(r["when"], sys_ctx):
            w = _subst(r["then"]["warn"], sys_ctx, project)
            warns.append({**w, "rule_code": r["code"], "rationale": r["rationale"]})

    # gộp dòng trùng mã
    merged = {}
    for l in lines:
        k = (l["layer"], l["part_number"])
        if k in merged:
            merged[k]["qty"] += l["qty"]
            # cộng dồn theo từng actuator, không chỉ hợp nhất tên
            fi = dict(merged[k].get("for_items") or {})
            for code_, q_ in (l.get("for_items") or {}).items():
                fi[code_] = fi.get(code_, 0) + q_
            merged[k]["for_items"] = fi
        else:
            merged[k] = dict(l)
    lines = list(merged.values())

    # ── ghi DB ──────────────────────────────────────────────────────────────
    for l in lines:
        p = con.execute("select id from part where part_number=?",
                        (l["part_number"],)).fetchone()
        con.execute(
            """insert into project_output (project_id, part_id, proposed_code, qty, layer,
                                           rule_code, rationale, confidence, status,
                                           alternatives)
               values (?,?,?,?,?,?,?,?,?,?)""",
            (pid, p["id"] if p else None, l["part_number"], l["qty"], l["layer"],
             l.get("rule_code"), l["rationale"], l.get("confidence"), "suggested",
             json.dumps(l.get("alternatives") or [], ensure_ascii=False)))
    for g in gaps:
        con.execute(
            """insert into project_output (project_id, qty, layer, rule_code, rationale,
                                           status, requirement)
               values (?,?,?,?,?,?,?)""",
            (pid, 0, "?", g.get("rule_code"), g.get("rationale", ""), "gap",
             json.dumps(g, ensure_ascii=False)))
    for w in warns:
        con.execute(
            """insert into project_warning (project_id, severity, code, message, detail)
               values (?,?,?,?,?)""",
            (pid, w.get("severity", "warn"), w.get("code", "?"), w.get("message", ""),
             json.dumps(w, ensure_ascii=False)))
    con.commit()

    return {"project_id": pid, "project": project, "lines": lines,
            "warnings": warns, "gaps": gaps, "calc": calcs, "system": sys_ctx}
