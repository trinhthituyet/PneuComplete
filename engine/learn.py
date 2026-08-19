"""Học lựa chọn của người dùng từ BOM đã có (+ về sau: thao tác sửa trong UI).

VÌ SAO KHÔNG PHẢI HỌC MÁY: 2 BOM thì thống kê là đoán. Nhưng điều đo được trên
chính dữ liệu này cho thấy có tín hiệu mạnh ở MỘT loại tri thức:

    speed controller push-lock (-A) : 69 cái, cả hai máy, nhất quán 100%

69 mẫu nhất quán 100% là bằng chứng chắc — và quan trọng hơn, nó nằm TRONG MỘT
BOM. Dùng 32 cái push-lock trong cùng một máy là 32 lần khẳng định, không cần máy
thứ hai. Đó là lý do học LỰA CHỌN được mà học SỐ LƯỢNG thì không:

    KQ2L / xy-lanh : 1.59 vs 4.62   (lệch 2.9×)
    KQ2U / xy-lanh : 1.76 vs 3.81   (lệch 2.2×)
    JA30 / xy-lanh : 0.29 vs 0.06   (lệch 4.8×)

RANH GIỚI KHÔNG ĐƯỢC VƯỢT: tri thức ở đây chỉ XẾP HẠNG giữa các phương án ĐÃ HỢP
LỆ. Đồ thị giao diện vẫn quyết định lắp được hay không. Học "thích push-lock" thì
tốt; "M5 lắp vào R1/8" phải bị chặn.

    python3 -m engine.learn              # xem đã học được gì
    python3 -m engine.learn --save       # ghi vào bảng learned_pref
    python3 -m engine.learn --forget     # xoá hết tri thức đã học
"""
import json
import re
import sys

from crawler import db

# ── Phân loại khoá: cái nào CHUYỂN được sang máy mới, cái nào không ──────────
#
# Phân loại này dựa trên số liệu đo trên 2 BOM thật (2026-08-19), không phải
# cảm tính. Cột "đo được" ghi giá trị quan sát ở máy 23-432 / 24-236.
#
# THÓI QUEN = thuộc tính của NGƯỜI MUA, không phụ thuộc máy → học và áp được.
HABIT_KEYS = {
    # đo: 100% push-lock trên 69 cái, cả hai máy. Tín hiệu mạnh nhất có được.
    "speed_controller_series",
    "speed_controller_knob",
    # đo: màu B ở cả hai máy
    "tube_color",
    # đo: cuộn 200 m ở cả hai máy
    "tube_roll_length_m",
    # đo: thế hệ -D ở cả hai máy (AC30…-D, AR30…-D)
    "frl_series",
}

# RIÊNG MÁY = phụ thuộc lưu lượng, layout hoặc thiết kế từng máy → PHẢI khai lại.
# Ghi ra tường minh để không ai lỡ đưa vào HABIT_KEYS.
MACHINE_KEYS = {
    # đo: 200 m vs 300 m — phụ thuộc layout
    "tube_total_m",
    # đo: body_ported vs base_mounted — khác nhau rõ, là quyết định thiết kế
    "valve_mounting",
    # chỉ máy 23-432 có
    "manifold_type", "use_manifold",
    # CẢNH BÁO N=2: mấy khoá dưới đây quan sát thấy GIỐNG nhau ở cả hai máy
    # (tube_od_mm=6.0, valve_series_size=SY5000), nhưng chúng do LƯU LƯỢNG quyết
    # định, không phải sở thích. Hai máy của bạn cỡ gần bằng nhau (17 và 16
    # xy-lanh) nên không tách được "thói quen" khỏi "trùng hợp vì máy giống cỡ".
    # Xếp vào RIÊNG MÁY là phía an toàn: đoán sai cỡ van là mua sai hàng.
    "tube_od_mm", "valve_series_size", "frl_size", "main_line_port_size",
    # phụ thuộc yêu cầu khí của từng máy
    "frl_lubricator", "frl_mist_separator", "frl_auto_drain",
    "frl_gauge", "frl_gauge_entry", "frl_gauge_output", "frl_relief_valve",
}

# Điều kiện để một tri thức được dùng làm mặc định cho máy MỚI.
# Tách hai ngưỡng vì hai loại bằng chứng khác nhau về chất:
#   MIN_MACHINES : thấy ở nhiều máy → đã chuyển được sang máy khác, bằng chứng tốt
#   MIN_REPEAT   : lặp rất nhiều trong MỘT máy cũng đủ (32 cái push-lock là thật),
#                  nhưng phải cao hơn nhiều vì chưa chứng minh chuyển được
MIN_MACHINES = 2
MIN_REPEAT = 10


def _ensure(con):
    """Tạo bảng learned_pref nếu DB cũ chưa có (project không có hệ migration)."""
    con.execute("""
        create table if not exists learned_pref (
          id integer primary key autoincrement,
          kind text not null, subject text not null,
          ctx_key text not null default '', ctx_level integer not null default 4,
          value text not null,
          n_support integer not null default 0, n_conflict integer not null default 0,
          evidence text, enabled integer not null default 1,
          updated_at text not null default (datetime('now')),
          unique (kind, subject, ctx_key))""")


# ── Trích lựa chọn từ một BOM ────────────────────────────────────────────────

def observe_machine(con, machine_id):
    """Đọc BOM một máy, trả {khoá: (giá_trị, số_bằng_chứng)}.

    Số bằng chứng tính theo SỐ LƯỢNG (qty), không theo số dòng: 24 cái
    AS1201F-M5-06A là 24 lần khẳng định "tôi dùng push-lock", không phải 1.
    """
    rows = con.execute(
        "select raw_code, qty from bom_line where machine_id=?", (machine_id,)).fetchall()
    votes = {}

    def vote(key, value, n):
        if value is None:
            return
        votes.setdefault(key, {}).setdefault(value, 0)
        votes[key][value] += n

    for r in rows:
        c = (r["raw_code"] or "").upper()
        n = float(r["qty"] or 1)

        # Speed controller: hậu tố A = push-lock. Đây là tín hiệu KHÔNG có trong
        # guess_project() — trước đây bị hardcode trong DEFAULT_PROJECT.
        m = re.match(r"^AS([12])\d{3}F-", c)
        if m:
            push = c.endswith("A")            # …-06A, …-06SA
            vote("speed_controller_series", "AS1-E" if push else "AS-E-E", n)
            vote("speed_controller_knob", "push_lock" if push else "standard", n)

        # Ống TU: màu và chiều dài cuộn
        m = re.match(r"^TU(\d{2})(\d{2})([A-Z]+\d?)-(\d+)$", c)
        if m:
            vote("tube_color", m.group(3), n)
            vote("tube_roll_length_m", float(m.group(4)), n)

        # Thế hệ FRL/regulator: hậu tố -A hay -D.
        # LOẠI AR10: họ này CHỈ có thế hệ -A (catalog AR10-A-E, không có bản -D),
        # nên AR10-…-A không phải một LỰA CHỌN — không có gì để chọn. Đếm nó vào
        # đây tạo ra mâu thuẫn giả và làm hạ tin cậy của tri thức đúng.
        if re.match(r"^A[CRF]\d{2}", c) and not c.startswith("AR10"):
            if c.endswith("-D"):
                vote("frl_series", "AC-D-E", n)
            elif c.endswith("-A"):
                vote("frl_series", "AC-A-E", n)

    # Trả TOÀN BỘ phân bố phiếu, không chỉ phương án thắng.
    # Lỗi đã mắc: trả max() làm mất phiếu thiểu số TRONG CÙNG một máy — BOM có
    # 3 cuộn màu B và 1 cuộn BU thì báo "mâu thuẫn 0", nghe như bạn tuyệt đối
    # nhất quán. Mâu thuẫn nội bộ một máy chính là tín hiệu mạnh nhất cho thấy
    # đây CHƯA phải thói quen chắc.
    return votes


# ── Tổng hợp qua nhiều máy ───────────────────────────────────────────────────

def learn(con, exclude=()):
    """Tổng hợp tri thức từ mọi máy TRỪ `exclude`. Trả list dict đọc được.

    `exclude` là chốt chống tự lừa: chấm điểm trên máy X thì phải học từ máy
    khác X. Học cả X rồi chấm trên X là đưa trước đáp án.
    """
    ex = set(exclude)
    agg = {}
    for m in con.execute("select id, name from machine").fetchall():
        if m["id"] in ex:
            continue
        for key, dist in observe_machine(con, m["id"]).items():
            a = agg.setdefault(key, {"values": {}, "machines": {}})
            for val, n in dist.items():
                a["values"][str(val)] = a["values"].get(str(val), 0) + n
                a["machines"].setdefault(str(val), set()).add(m["name"])

    out = []
    for key, a in sorted(agg.items()):
        ranked = sorted(a["values"].items(), key=lambda kv: -kv[1])
        top_val, top_n = ranked[0]
        conflict = sum(n for _, n in ranked[1:])
        machines = sorted(a["machines"].get(top_val, set()))
        out.append({
            "kind": "config",
            "subject": key,
            "ctx_key": "",
            "ctx_level": 4,
            "value": top_val,
            "n_support": int(top_n),
            "n_conflict": int(conflict),
            "machines": machines,
            "n_machines": len(machines),
            "transferable": key in HABIT_KEYS,
            # Mâu thuẫn thì KHÔNG lấy trung bình. Trung bình của 1 và 14 là 7 —
            # con số không tồn tại trong thực tế. Hạ tin cậy và để engine hỏi.
            # Ba điều kiện, thiếu một là không dùng:
            #   · thuộc nhóm THÓI QUEN (chuyển được giữa các máy)
            #   · mâu thuẫn ≤ 1/2 số ủng hộ — mâu thuẫn thì HỎI, không lấy trung bình
            #   · đủ bằng chứng: thấy ở ≥2 máy, HOẶC lặp rất nhiều (≥10) trong 1 máy.
            #     Phân biệt này cần thiết: 32 cái push-lock trong một máy là bằng
            #     chứng thật, còn 4 cái trong một máy thì chưa nói được gì.
            "usable": (key in HABIT_KEYS
                       and conflict * 2 <= top_n
                       and (len(machines) >= MIN_MACHINES or top_n >= MIN_REPEAT)),
        })
    return out


def save(con, prefs):
    """Ghi tri thức vào learned_pref. Giữ nguyên `enabled` người dùng đã tắt."""
    _ensure(con)
    n = 0
    for p in prefs:
        con.execute(
            """insert into learned_pref
                 (kind, subject, ctx_key, ctx_level, value, n_support, n_conflict, evidence)
               values (?,?,?,?,?,?,?,?)
               on conflict (kind, subject, ctx_key) do update set
                 value=excluded.value, n_support=excluded.n_support,
                 n_conflict=excluded.n_conflict, evidence=excluded.evidence,
                 ctx_level=excluded.ctx_level, updated_at=datetime('now')""",
            (p["kind"], p["subject"], p["ctx_key"], p["ctx_level"],
             json.dumps(p["value"], ensure_ascii=False),
             p["n_support"], p["n_conflict"],
             json.dumps({"machines": p.get("machines", []),
                         "transferable": p.get("transferable"),
                         "usable": p.get("usable")}, ensure_ascii=False)))
        n += 1
    con.commit()
    return n


def preferences(con, exclude=()):
    """Trả {khoá: giá_trị} dùng được — CHỈ khoá thói quen, đủ bằng chứng, không mâu thuẫn.

    Đây là hàm engine gọi. Nó KHÔNG đọc learned_pref mà tính lại từ BOM: giữ một
    nguồn sự thật duy nhất, tránh cảnh bảng lưu bị lệch với dữ liệu. learned_pref
    dùng để NGƯỜI XEM và tắt từng mục.
    """
    _ensure(con)
    off = {r["subject"] for r in con.execute(
        "select subject from learned_pref where enabled=0").fetchall()}
    out = {}
    for p in learn(con, exclude=exclude):
        if p["usable"] and p["subject"] not in off:
            v = p["value"]
            # value lưu dạng chuỗi; trả lại đúng kiểu cho engine dùng
            try:
                v = float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else v
            except (TypeError, ValueError):
                pass
            out[p["subject"]] = v
    return out


def main(argv):
    con = db.connect()
    if "--forget" in argv:
        _ensure(con)
        n = con.execute("delete from learned_pref").rowcount
        con.commit()
        print(f"Đã xoá {n} mục tri thức đã học.")
        return 0

    prefs = learn(con)
    if not prefs:
        print("Chưa học được gì — chưa có BOM nào trong DB.")
        print("Nhập BOM cũ: python3 -m ingest.bom_import BOM/*.xlsx")
        return 0

    print("TRI THỨC HỌC ĐƯỢC TỪ BOM ĐÃ CÓ")
    print("=" * 78)
    print(f"{'lựa chọn':28} {'giá trị':14} {'b.chứng':>8} {'mâu thuẫn':>10}  dùng được")
    print("-" * 78)
    for p in prefs:
        mark = "✓ CÓ" if p["usable"] else ("· riêng máy" if not p["transferable"]
                                          else "· chưa đủ")
        print(f"{p['subject']:28} {str(p['value'])[:14]:14} "
              f"{p['n_support']:>8} {p['n_conflict']:>10}  {mark}")
    print()
    usable = [p for p in prefs if p["usable"]]
    print(f"  {len(usable)}/{len(prefs)} lựa chọn đủ điều kiện áp cho máy mới")
    print(f"  điều kiện: thuộc nhóm THÓI QUEN · mâu thuẫn ≤ 1/2 số ủng hộ ·")
    print(f"             thấy ở ≥{MIN_MACHINES} máy HOẶC lặp ≥{MIN_REPEAT} lần trong 1 máy")
    for p in usable:
        print(f"    · {p['subject']} = {p['value']}  (học từ: {', '.join(m[:14] for m in p['machines'])})")

    if "--save" in argv:
        print(f"\n✓ Đã ghi {save(con, prefs)} mục vào bảng learned_pref")
    else:
        print("\n  (thêm --save để ghi vào DB)")
    con.close()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(db.ROOT))
    sys.exit(main(sys.argv[1:]))
