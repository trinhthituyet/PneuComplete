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
from engine import calc, conf, generate, learn, materialize
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
    "frl_size": None,            # khai nếu muốn chốt cỡ AC (10/20/25/30/40)
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
def _resolve_need(con, need, ctx, project, src_part_id, templates):
    """REQUIREMENT → dòng BOM cụ thể, hoặc gap kèm lý do."""
    # luật có thể khai thông tin BẮT BUỘC người dùng cấp. Không có thì gap —
    # tuyệt đối không lấy giá trị mặc định do engine tự nghĩ ra (A3-5).
    ri = need.get("requires_input")
    if ri and project.get(ri) in (None, ""):
        return {"gap": f"cần bạn khai `{ri}` — engine không suy được giá trị này"}
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


def build(con, inputs, project=None, project_name="demo", learn_exclude=None,
          use_learned=True):
    """inputs: [(mã, số_lượng)] hoặc [(mã, số_lượng, {override})].

    Override theo TỪNG actuator cần thiết vì loại van phụ thuộc CHỨC NĂNG của cơ
    cấu, không phải loại xy-lanh: cơ cấu kẹp dùng van 5/2 single, cơ cấu đi-về có
    dừng giữa dùng 3-position. Golden test trên máy 23-432 cho thấy một máy dùng
    đồng thời SY5120 (single) ×5, SY5220 (double) ×2, SY5420 (3-pos exhaust) ×4 —
    luật chung "mỗi xy-lanh một van 5/2 double" sai với thực tế.
    """
    # THỨ TỰ ƯU TIÊN CẤU HÌNH — tường minh, vì đây là chỗ dễ sai nhất khi thêm
    # tri thức học được:
    #
    #   DEFAULT_PROJECT   mặc định trung tính về kỹ thuật (áp suất, chu kỳ)
    #     ← learned       thói quen học từ BOM cũ của bạn (engine/learn.py)
    #     ← project       cấu hình bạn khai lần này  ← LUÔN THẮNG
    #
    # Tri thức học được KHÔNG BAO GIỜ ghi đè điều bạn khai tường minh. Nếu ngược
    # lại thì người dùng mất quyền điều khiển, và tệ hơn là mất một cách âm thầm.
    #
    # learn_exclude: bỏ các máy này khỏi việc học. Dùng cho golden test kiểu
    # bỏ-ra-một-máy — học từ chính máy đang chấm là tự đưa trước đáp án.
    # Sở thích chưa khai và chưa học được thì xử lý thế nào? Phân biệt theo HẬU QUẢ
    # của việc đoán sai, không theo "có phải sở thích hay không":
    #
    #   NEED_EVIDENCE   đoán sai làm lệch SỐ LƯỢNG → báo gap, tuyệt đối không đoán
    #   WARN_IF_GUESSED đoán sai chỉ lệch BIẾN THỂ (hậu tố), số lượng vẫn đúng
    #                   → vẫn ra dòng + cảnh báo rõ phải kiểm chỗ nào
    #
    # VÌ SAO tách: golden test bỏ-ra-một-máy cho thấy mặc định 20 m cuộn làm engine
    # đề xuất `TU0604BU-20 ×15` trong khi thực tế `TU0604B-200 ×1` — sai 15 lần số
    # lượng. Không đoán được thì thà thiếu dòng.
    # Nhưng bỏ luôn cả dòng speed controller thì mất giá trị chính của phần mềm là
    # "không bỏ sót vật tư", trong khi đoán sai hậu tố A chỉ tốn một lần kiểm lại.
    # Số lượng vẫn đúng, và đúng số lượng mới là chỗ tốn tiền.
    NEED_EVIDENCE = ("tube_roll_length_m",)
    WARN_IF_GUESSED = ("tube_color", "speed_controller_series",
                       "speed_controller_knob", "frl_series")

    # use_learned=False: bỏ hẳn phần học. Cần cho test — kết quả engine không được
    # phụ thuộc vào việc DB đang có BOM nào. Không có cờ này thì thêm một BOM vào
    # DB là làm đổi kết quả test, và người sửa test sẽ không hiểu vì sao.
    learned, learn_err = {}, None
    try:
        if use_learned:
            learned = learn.preferences(con, exclude=learn_exclude or ())
    except Exception as e:
        # Học được là tốt, không học được thì engine vẫn phải chạy — tri thức là
        # phần tăng thêm, không phải điều kiện để dựng BOM.
        # Nhưng KHÔNG im lặng: nuốt lỗi ở đây thì một lỗi trong learn.py sẽ chỉ
        # biểu hiện thành "BOM hơi khác trước" mà không ai lần ra được.
        learn_err = f"{type(e).__name__}: {e}"
    explicit = project or {}
    project = {**DEFAULT_PROJECT, **learned, **explicit}
    # Khoá nào chỉ có giá trị nhờ mặc định hardcode → coi như CHƯA BIẾT.
    unknown_pref = [k for k in NEED_EVIDENCE
                    if k not in explicit and k not in learned]
    for k in unknown_pref:
        project[k] = None
    guessed_pref = [k for k in WARN_IF_GUESSED
                    if k not in explicit and k not in learned]
    templates = materialize.load_templates()
    materialize.seed_thread_compat(con)

    cur = con.execute("insert into project (name, config) values (?,?)",
                      (project_name, json.dumps(project, ensure_ascii=False)))
    pid = cur.lastrowid
    prune_projects(con)

    lines, warns, gaps, calcs = [], [], [], []
    if learn_err:
        warns.append({"severity": "warn", "code": "LEARN_FAILED",
                      "message": f"Không đọc được tri thức đã học: {learn_err}. "
                                 f"BOM vẫn dựng bằng mặc định.",
                      "detail": learn_err})
    elif learned:
        warns.append({"severity": "info", "code": "LEARNED_APPLIED",
                      "message": "Áp thói quen học từ BOM cũ: "
                                 + ", ".join(f"{k}={v}" for k, v in sorted(learned.items())),
                      "detail": learned})
    if guessed_pref:
        warns.append({
            "severity": "warn", "code": "PREF_GUESSED",
            "message": ("Các lựa chọn sau dùng MẶC ĐỊNH vì bạn chưa khai và engine "
                        "chưa học được từ BOM cũ — hãy kiểm lại hậu tố mã hàng: "
                        + ", ".join(f"{k}={project.get(k)}" for k in guessed_pref)
                        + ". Số lượng không bị ảnh hưởng. Nhập BOM máy cũ "
                          "(python3 -m ingest.bom_import) để engine học đúng thói quen."),
            "detail": {k: project.get(k) for k in guessed_pref}})
    for k in unknown_pref:
        gaps.append({
            "rule_code": "R-PREF-00",
            "requirement": k,
            # khoá "reason" là hình dạng chung của mọi gap trong engine — thiếu nó
            # thì UI và test không đọc được. Test đã bắt đúng lỗi này.
            "reason": f"chưa biết lựa chọn cho '{k}'",
            "rationale": (
                f"Chưa biết bạn chọn gì cho '{k}'. Engine KHÔNG đoán vì đoán sai "
                f"là mua sai hàng. Hai cách khắc phục: khai trực tiếp ở mục cấu "
                f"hình, hoặc nhập BOM máy cũ để engine học "
                f"(python3 -m ingest.bom_import <tệp.xlsx>)."),
        })
    per_act = load_rules(con, "per_actuator")
    onetouch_open = 0
    # Đếm đầu one-touch THEO TỪNG ĐƯỜNG KÍNH. Máy thật dùng nhiều cỡ ống cùng lúc
    # (BOM 23-432: TU0604B-200 cho nhánh xy-lanh + TU1065B-100 cho trục chính),
    # gộp thành một số thì engine chỉ đề xuất được một loại ống.
    onetouch_by_od = defaultdict(float)

    for item in inputs:
        code, count = item[0], item[1]
        over = item[2] if len(item) > 2 else {}
        con.execute("""insert into project_input (project_id, raw_code, qty, overrides)
                       values (?,?,?,?)""",
                    (pid, code, count, json.dumps(over, ensure_ascii=False)))
        item_project = _expand_valve_function({**project, **over})
        m = materialize.materialize(con, code, templates)
        if not m["ok"]:
            gaps.append({"item": code, "reason": m["error"]})
            continue

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
                gaps.append({"item": code, "rule_code": r["code"],
                             "reason": res["gap"], "rationale": r["rationale"]})
                continue
            lines.append({"layer": need["layer"], "part_number": res["part_number"],
                          "qty": res["qty"] * count, "rule_code": r["code"],
                          "rationale": r["rationale"], "confidence": res["confidence"],
                          "note": res.get("note"),
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

    # ── CONSOLIDATE toàn hệ ─────────────────────────────────────────────────
    roll = project["tube_roll_length_m"]
    # KHÔNG ước lượng chiều dài ống (A3-5). Chỉ tính khi người dùng đã khai tổng mét.
    total_m = project.get("tube_total_m")
    # roll có thể là None: chiều dài cuộn là SỞ THÍCH MUA HÀNG, nằm trong
    # NEED_EVIDENCE — chưa khai và chưa học được thì không đoán. Trước đây rơi về
    # mặc định 20 m và cho ra "TU0604BU-20 ×15" trong khi thực tế là 1 cuộn 200 m.
    rolls = math.ceil(total_m / roll) if (total_m and roll) else None
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
            gaps.append({"rule_code": r["code"],
                         "reason": f"{g['what']} — {' '.join(g['reason'].split())}",
                         "rationale": r["rationale"]})
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
                # roll có thể None (sở thích chưa khai/chưa học) — không đoán
                ctx_v["tube_rolls_needed"] = (
                    max(1, math.ceil(m_v / roll)) if (m_v and roll) else None)
                ctx_v["tube_od_mm"] = od
            res = _resolve_need(con, need, ctx_v, proj_v, None, templates)
            if "gap" in res:
                gaps.append({"rule_code": r["code"], "reason": res["gap"],
                             "rationale": r["rationale"]})
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
