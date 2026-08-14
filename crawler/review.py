"""Sinh phiếu duyệt A3 và ghi nhận quyết định.

    python3 -m crawler.review sheet              → docs/REVIEW-A3.md
    python3 -m crawler.review ok   A3-1          → đánh dấu đúng
    python3 -m crawler.review no   A3-1 "lý do"  → đánh dấu sai
    python3 -m crawler.review status             → còn bao nhiêu chưa duyệt

Phiếu chỉ đọc dữ liệu THẬT trong DB nên không thể lệch với cái engine đang dùng.
Phần "cần xác nhận" là các suy diễn của tôi — chỗ dễ sai nhất, ưu tiên duyệt trước.
"""
import json
import sys

from . import db

# Các giá trị tôi SUY, không đọc trực tiếp từ catalog. Đây là danh sách rủi ro thật.
CLAIMS = [
    dict(id="A3-1", risk="cao", area="engine/calc.py rod_dia_mm",
         claim="Cột 'D' của bảng kích thước PDF CM2 trang 14 là ĐƯỜNG KÍNH CẦN: "
               "bore 20→ø8, 25→ø10, 32→ø12, 40→ø14",
         read="Số liệu đọc trực tiếp từ bảng (map cột theo toạ độ header, D ở x=122)",
         inferred="Việc cột 'D' nghĩa là đường kính cần — tôi không xem được bản vẽ. "
                  "Bản trước tôi ghi bore 40 → ø16 theo trí nhớ, bảng thật ghi 14.",
         impact="Sai → LỰC KÉO tính sai (lực đẩy không ảnh hưởng). Với ø40 chênh "
                "551 N vs 503 N nếu thực tế là ø16.",
         howto="Mở PDF CM2 trang 14, xem bản vẽ: ký hiệu D trỏ vào đường kính cần "
               "hay kích thước khác?"),
    dict(id="A3-2", risk="cao", area="db/seed/grammar/d-m9.yaml",
         claim="Quy ước đặt tên D-M9: N=3-wire NPN, P=3-wire PNP, B=2-wire, "
               "W=2-color indicator, A=water resistant, V=perpendicular entry",
         read="38 mã (M9N, M9BW, A93V…) đọc trực tiếp từ bảng Applicable Auto "
              "Switches, PDF CM2 trang 6. Chiều dài dây Nil/M/L/Z cũng đọc trực tiếp.",
         inferred="Ý nghĩa từng chữ cái — tôi đối chiếu với các dòng của bảng "
                  "('3-wire (NPN)', '2-wire', 'Diagnostic indication (2-color)') "
                  "nhưng bảng bị -layout làm sập nên không khớp được từng ô chắc chắn.",
         impact="Sai → engine chọn sai loại cảm biến. Ví dụ cần PNP mà ra NPN thì "
                "không đọc được tín hiệu vào PLC.",
         howto="Với xy-lanh CM2, cảm biến D-M9BW có đúng là 2-wire, 2-color "
               "indicator, ra dây thẳng (grommet) không?"),
    dict(id="A3-3", risk="trung bình", area="db/seed/grammar/tu.yaml",
         claim="Mã ống TU0425 nghĩa là OD ø4 / ID ø2.5; TU0604 = OD6/ID4; "
               "TU0805 = OD8/ID5; TU1065 = OD10/ID6.5; TU1208 = OD12/ID8",
         read="Danh sách mã TU0425/TU0604/TU0805/TU1065/TU1208 đọc từ bảng "
              "'Made to Order Availability', PDF TU trang 2.",
         inferred="Cách giải nghĩa 4 chữ số thành OD/ID — theo quy ước, không đọc "
                  "được bảng OD/ID tường minh trong 2 trang PDF này.",
         impact="Sai → chọn ống sai cỡ, không cắm được vào đầu one-touch ø6.",
         howto="Ống TU0604 có đúng là ngoài ø6, trong ø4 không?"),
    dict(id="A3-4", risk="trung bình", area="db/seed/grammar/d-m9.yaml",
         claim="Ký hiệu chiều dài dây 'N' = không có dây (loại connector)",
         read="Chú thích PDF CM2 trang 6 có dãy '(Nil) (M) (L) (Z) (N)' và ghi rõ "
              "0.5m=Nil, 1m=M, 3m=L, 5m=Z.",
         inferred="Riêng 'N' không có chú thích chiều dài → tôi suy là 'không dây'.",
         impact="Thấp — engine mặc định dùng Nil (0.5 m), không tự chọn N.",
         howto="Bỏ qua được nếu bạn không dùng loại connector."),
    dict(id="A3-5", risk="trung bình", area="db/seed/rules.yaml R-TUBE-01",
         claim="Mỗi đầu one-touch cần ~3 m ống → 10 đầu = 30 m = 2 cuộn 20 m",
         read="Không đọc từ đâu cả.",
         inferred="Con số 3 m là tôi đặt ra làm mặc định. Engine đã ghi rõ trong "
                  "rationale rằng đây là ƯỚC LƯỢNG.",
         impact="Sai → thiếu hoặc thừa ống. Không nguy hiểm nhưng lệch chi phí.",
         howto="Với máy của bạn, trung bình mỗi mối nối cần bao nhiêu mét ống?"),
    dict(id="A3-6", risk="thấp", area="engine/bom.py ctx['acting']",
         claim="CM2 là xy-lanh tác động 2 chiều (double acting) — engine gán cứng",
         read="Bảng variation HTML của trang series CM2 ghi 'Double acting, Single "
              "rod' và 'Single acting (Spring return/extend)' — CÓ CẢ HAI loại.",
         inferred="Engine đang gán cứng 'double' cho mọi mã CM2. Mã CM2 loại single "
                  "acting có ký hiệu riêng mà ngữ pháp hiện tại chưa phân biệt.",
         impact="Nhập mã xy-lanh single-acting → engine vẫn đề xuất 2 speed "
                "controller và van 5/2, trong khi chỉ cần 1 và van 3/2.",
         howto="Bạn có dùng xy-lanh single acting (hồi lò xo) không? Nếu có thì đây "
               "là lỗi cần sửa trước khi dùng thật."),
    dict(id="A3-7", risk="thấp", area="db/seed/interfaces.yaml CM2 rod_end",
         claim="Ren đầu cần: bore 20→M8x1.25, 25→M10x1.25, 32→M10x1.25, 40→M14x1.5",
         read="ĐỌC TRỰC TIẾP cột MM của bảng kích thước PDF trang 14. Cả 4 giá trị.",
         inferred="Không suy gì. Chỉ cần bạn xác nhận cột 'MM' là ren đầu cần.",
         impact="Sai → chọn sai joint/knuckle đầu cần (chưa có trong BOM hiện tại).",
         howto="Xem bản vẽ trang 14: MM có phải ren đầu cần?"),
]


def ensure_table(con):
    con.execute("""create table if not exists a3_decision (
        claim_id text primary key, verdict text check (verdict in ('ok','no')),
        note text, decided_at text default (datetime('now')))""")
    con.commit()


def sheet(con):
    ensure_table(con)
    decided = {r["claim_id"]: r for r in con.execute("select * from a3_decision")}
    L = []
    w = L.append
    w("# Phiếu duyệt A3 — dữ liệu cần bạn xác nhận\n")
    w("Sinh tự động từ DB thật (`python3 -m crawler.review sheet`). Ước lượng 1 giờ.\n")
    w("Mục đích: 4 series đã có ngữ pháp đều do tôi đọc PDF, chưa ai kiểm. "
      "Trước khi mở rộng thêm series (giai đoạn B), cần biết cái đang có có đúng không "
      "— nếu không thì mở rộng chỉ nhân rộng cái sai.\n")
    w("Ghi quyết định:\n```\npython3 -m crawler.review ok A3-1\n"
      "python3 -m crawler.review no A3-1 \"cột D là đường kính ngoài ống, không phải cần\"\n```\n")

    w("\n## Phần 1 — CẦN XÁC NHẬN (ưu tiên theo rủi ro)\n")
    order = {"cao": 0, "trung bình": 1, "thấp": 2}
    for c in sorted(CLAIMS, key=lambda c: order[c["risk"]]):
        d = decided.get(c["id"])
        mark = {"ok": "[x] ĐÚNG", "no": "[!] SAI"}.get(d["verdict"], "[ ]") if d else "[ ]"
        w(f"\n### {mark} {c['id']} · rủi ro {c['risk']} · `{c['area']}`\n")
        w(f"**Tôi đang dùng:** {c['claim']}\n")
        w(f"- ✅ đọc được từ catalog: {c['read']}")
        w(f"- ⚠️ phần tôi suy: {c['inferred']}")
        w(f"- 💥 nếu sai: {c['impact']}")
        w(f"- ❓ cách kiểm: {c['howto']}")
        if d and d["note"]:
            w(f"- 📝 bạn ghi: {d['note']}")

    w("\n\n## Phần 2 — Ngữ pháp đang dùng (đối chiếu nhanh với catalog)\n")
    for s in con.execute("""select s.id, s.code, s.catalog_id, s.notes from series s
                            where exists (select 1 from code_slot cs where cs.series_id=s.id)
                            order by s.code"""):
        src = (s["notes"] or "").split("nguồn:")[-1].strip()[:150]
        w(f"\n### {s['code']}  (`{s['catalog_id']}`)")
        if src:
            w(f"nguồn: {src}\n")
        for cs in con.execute("""select cs.pos, cs.name, cs.value_type, cs.separator, cs.id
                                 from code_slot cs where cs.series_id=? order by cs.pos""",
                              (s["id"],)):
            opts = con.execute("select code, label from code_option where slot_id=? order by id",
                               (cs["id"],)).fetchall()
            head = f"- **ô {cs['pos']} {cs['name']}** ({cs['value_type']}"
            head += f", ngăn cách `{cs['separator']}`" if cs["separator"] else ""
            head += f") — {len(opts)} lựa chọn"
            w(head)
            shown = opts[:14]
            for o in shown:
                w(f"    - `{o['code']}` = {o['label'] or '(không nhãn)'}")
            if len(opts) > len(shown):
                w(f"    - … còn {len(opts)-len(shown)} lựa chọn nữa")

    w("\n\n## Phần 3 — Mã engine sinh ra, kiểm bằng mắt\n")
    w("| mã | nghĩa engine hiểu |")
    w("|---|---|")
    from engine import parser as P
    for pn in ("CDM2L32-500Z", "CDM2B40-150AZ", "AS2201F-01-06S", "AS2201F-02-06S",
               "TU0604BU-20", "D-M9BW"):
        r = P.parse(con, pn)
        if r.get("ok"):
            bits = ", ".join(f"{k}={v}" for k, v in r["attrs"].items())
            w(f"| `{pn}` | {bits} |")
    return "\n".join(L)


def main(argv):
    con = db.connect()
    ensure_table(con)
    cmd = argv[0] if argv else "status"
    if cmd == "sheet":
        out = db.ROOT / "docs" / "REVIEW-A3.md"
        out.write_text(sheet(con), encoding="utf-8")
        print(f"đã ghi {out}  ({len(CLAIMS)} mục cần xác nhận)")
    elif cmd in ("ok", "no"):
        cid = argv[1].upper()
        note = argv[2] if len(argv) > 2 else None
        if cid not in {c["id"] for c in CLAIMS}:
            print(f"không có mục {cid}")
            return 1
        con.execute("""insert into a3_decision (claim_id, verdict, note) values (?,?,?)
                       on conflict (claim_id) do update set verdict=excluded.verdict,
                       note=excluded.note, decided_at=datetime('now')""", (cid, cmd, note))
        con.commit()
        print(f"{cid} → {'ĐÚNG' if cmd == 'ok' else 'SAI'}" + (f" ({note})" if note else ""))
    else:
        d = {r["claim_id"]: r["verdict"] for r in con.execute("select * from a3_decision")}
        for c in CLAIMS:
            v = d.get(c["id"])
            print(f"  {'✓' if v == 'ok' else ('✗' if v == 'no' else '·')} {c['id']} "
                  f"[{c['risk']:11}] {c['claim'][:64]}")
        print(f"\n  {len(d)}/{len(CLAIMS)} đã duyệt")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
