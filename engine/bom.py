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
from pathlib import Path

import yaml

from crawler import db
from engine import calc, generate, materialize
from engine import parser as P

RULES_YAML = db.ROOT / "db" / "seed" / "rules.yaml"

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
    "switch_wiring": "2-wire",
    "switch_indicator": "2-color",
    "switch_lead_wire_m": 0.5,
    "safety_factor": 1.5,
}


# ── nạp luật ────────────────────────────────────────────────────────────────
def seed_rules(con):
    rules = yaml.safe_load(RULES_YAML.read_text(encoding="utf-8"))
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
def _resolve_need(con, need, ctx, project, src_part_id, templates):
    """REQUIREMENT → dòng BOM cụ thể, hoặc gap kèm lý do."""
    want = {k: v for k, v in (_subst(need.get("want", {}), ctx, project) or {}).items()
            if v is not None}
    qty = _subst(need.get("qty", 1), ctx, project) or 1

    # (a) chọn từ mã thật đã có trong bảng part (dùng khi chưa giải mã được ngữ pháp)
    if need.get("from_parts"):
        sid = con.execute("select id from series where catalog_id=?",
                          (need["from_parts"],)).fetchone()
        if not sid:
            return {"gap": f"không có series {need['from_parts']}"}
        rows = con.execute("select * from part where series_id=?", (sid["id"],)).fetchall()
        cands = []
        for r in rows:
            a = json.loads(r["attrs"] or "{}")
            if all(str(a.get(k)) == str(v) for k, v in want.items()):
                cands.append((a.get(need.get("rank_by", ""), 0) or 0, r, a))
        if not cands:
            return {"gap": f"không mã nào trong {need['from_parts']} thoả {want}"}
        cands.sort(key=lambda x: -x[0])
        best = cands[0]
        return {"part_number": best[1]["part_number"], "qty": qty,
                "attrs": best[2], "confidence": 0.6,
                "alternatives": [c[1]["part_number"] for c in cands[1:4]],
                "note": f"chọn theo tần suất trong catalog ({best[0]} lần); "
                        f"mã chưa giải mã hết nên is_verified=0"}

    # (b) sinh mã từ ngữ pháp
    sid = con.execute("select id from series where catalog_id=?",
                      (need["from_series"],)).fetchone()
    if not sid:
        return {"gap": f"không có series {need['from_series']}"}
    g = generate.generate(con, sid["id"], want)
    if not g.get("ok"):
        if g.get("error"):
            return {"gap": f"{need['from_series']}: {g['error']}"}
        bits = "; ".join(f"{u['slot']} ({u['reason']})" for u in g["undecided"])
        return {"gap": f"{need['from_series']}: chưa quyết được ô {bits}"}

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
def build(con, inputs, project=None, project_name="demo"):
    """inputs: [(mã_actuator, số_lượng), …]"""
    project = {**DEFAULT_PROJECT, **(project or {})}
    templates = materialize.load_templates()
    materialize.seed_thread_compat(con)

    cur = con.execute("insert into project (name, config) values (?,?)",
                      (project_name, json.dumps(project, ensure_ascii=False)))
    pid = cur.lastrowid

    lines, warns, gaps, calcs = [], [], [], []
    per_act = load_rules(con, "per_actuator")
    onetouch_open = 0

    for code, count in inputs:
        con.execute("insert into project_input (project_id, raw_code, qty) values (?,?,?)",
                    (pid, code, count))
        m = materialize.materialize(con, code, templates)
        if not m["ok"]:
            gaps.append({"item": code, "reason": m["error"]})
            continue

        a = m["attrs"]
        ports = con.execute(
            "select qty from part_interface where part_id=? and role='air_port'",
            (m["part_id"],)).fetchone()
        c = calc.summary(a.get("bore_mm"), a.get("stroke_mm"),
                         project["pressure_mpa"], project["cycle_s"], count,
                         project["safety_factor"]) if a.get("bore_mm") else {}
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
        }
        lines.append({"layer": "actuator", "part_number": m["part_number"],
                      "qty": count, "rule_code": None,
                      "rationale": "do người dùng nhập", "confidence": 1.0})

        for r in per_act:
            if not matches(r["when"], ctx):
                continue
            if "warn" in r["then"]:
                w = _subst(r["then"]["warn"], ctx, project)
                warns.append({**w, "rule_code": r["code"], "item": code,
                              "rationale": r["rationale"]})
                continue
            need = r["then"].get("need")
            if not need:
                continue
            res = _resolve_need(con, need, ctx, project, m["part_id"], templates)
            if "gap" in res:
                gaps.append({"item": code, "rule_code": r["code"],
                             "reason": res["gap"], "rationale": r["rationale"]})
                continue
            lines.append({"layer": need["layer"], "part_number": res["part_number"],
                          "qty": res["qty"] * count, "rule_code": r["code"],
                          "rationale": r["rationale"], "confidence": res["confidence"],
                          "note": res.get("note"),
                          "alternatives": res.get("alternatives")})
            if need["from_series"] == "AS-E-E" if need.get("from_series") else False:
                onetouch_open += res["qty"] * count

    # ── CONSOLIDATE toàn hệ ─────────────────────────────────────────────────
    import math
    est_run_m = project.get("tube_run_m_per_port", 3.0)
    roll = project["tube_roll_length_m"]
    sys_ctx = {
        "actuator_count": sum(n for _, n in inputs),
        "valve_count": sum(l["qty"] for l in lines if l["layer"] == "valve"),
        "open_onetouch_count": onetouch_open,
        "tube_rolls_needed": max(1, math.ceil(onetouch_open * est_run_m / roll)),
        "required_flow_lpm": round(sum(c.get("required_flow_lpm", 0) for c in calcs), 1),
        "total_flow_lpm": round(sum(c.get("total_flow_lpm", 0) for c in calcs), 1),
        "incompatible_thread_pairs": _count_bad_threads(con, lines),
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
            gaps.append({"rule_code": r["code"],
                         "reason": f"{g['what']} — {' '.join(g['reason'].split())}",
                         "rationale": r["rationale"]})
            continue
        need = r["then"].get("need")
        if not need:
            continue
        res = _resolve_need(con, need, sys_ctx, project, None, templates)
        if "gap" in res:
            gaps.append({"rule_code": r["code"], "reason": res["gap"],
                         "rationale": r["rationale"]})
            continue
        lines.append({"layer": need["layer"], "part_number": res["part_number"],
                      "qty": res["qty"], "rule_code": r["code"],
                      "rationale": r["rationale"], "confidence": res["confidence"],
                      "note": res.get("note"), "unit": need.get("unit")})

    # gộp dòng trùng mã
    merged = {}
    for l in lines:
        k = (l["layer"], l["part_number"])
        if k in merged:
            merged[k]["qty"] += l["qty"]
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
