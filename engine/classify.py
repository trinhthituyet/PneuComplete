"""Gõ MÃ HÀNG → phần mềm tự biết đó là thiết bị gì và gắn được vào đâu.

    >>> classify(con, "KQ2L06-02NS")
    {'ok': True, 'node_type': 'fitting', 'label': 'Đầu nối', 'layer': 'piping',
     'series': 'KQ2-E', 'allowed_parents': ['cylinder', 'valve', …], 'why': …}

VÌ SAO CÓ TỆP NÀY: bạn nói "tôi muốn thêm mã rồi phần mềm tự phân loại". Trước đây
thêm thiết bị là chọn LOẠI từ danh sách rồi mới gõ mã — người dùng phải tự biết
KQ2 là "đầu nối" còn AS…F là "tiết lưu", tức phải biết sẵn cái mà phần mềm này có
nhiệm vụ biết hộ.

── ĐÃ ĐO: HAI CÁCH PHÂN LOẠI SAI, VÀ VÌ SAO ─────────────────────────────────
1. THEO `category.layer` CỦA CRAWL — KHÔNG DÙNG ĐƯỢC.
   48 mã BOM khách hàng có layer, chỉ 5 mã suy ra được DUY NHẤT một loại node.
   Vì layer là cách xếp nhóm BÁO GIÁ, nhiều loại thiết bị chung một layer:
     layer 'valve'  → van · đế manifold · gasket · end plate
     layer 'piping' → đầu nối · ống · giảm âm
   Và layer trong DB còn SAI THẬT: AS (tiết lưu) bị xếp 'electrical',
   AC/AR-D (xử lý khí) xếp 'other'. Crawl lấy theo cây menu website, không theo
   chức năng thiết bị.

2. THEO TIỀN TỐ MÃ — KHÔNG DÙNG ĐƯỢC.
   'AS' là tiết lưu nhưng 'AS' cũng mở đầu nhiều họ khác; 'SY5000-GS-1' (gasket)
   cùng tiền tố với 'SY5220-5MZE-C6' (van). Suy theo chuỗi là đoán.

── CÁCH LÀM: KHAI TƯỜNG MINH, KÈM CỔNG ──────────────────────────────────────
Toàn bộ thứ người dùng gõ mã vào được là 19 series CÓ NGỮ PHÁP (đo trong DB), nên
bảng khai tay chỉ 19 dòng — rẻ hơn mọi kiểu suy đoán, và ĐÚNG.
Cổng ở tests/test_graph.py: series nào có ngữ pháp mà thiếu dòng ở đây thì test
ĐỎ. Nhờ vậy thêm ngữ pháp mới mà quên phân loại không lọt được.

VAI TRÒ THẮNG SERIES: 'SY5000-GS-1' parse ra series SY-5-E (van) nhưng bảng tra
catalog ghi role='gasket' — nó là PHỤ KIỆN ĐẾ, không phải van. Mã cụ thể luôn nói
đúng hơn họ chứa nó.
"""
from engine import graph as G
from engine import parser as P
from engine import tree as T

# catalog_id của series → loại node trên sơ đồ.
# CHỈ những series có ngữ pháp (gõ mã vào được). Cổng G-CLASS-01 giữ cho danh sách
# này không tụt lại sau DB.
SERIES_NODE_TYPE = {
    "AC-A-E": "frl",              # Modular F.R.L. Unit
    "AC-D-E": "frl",
    "AR-D-E": "regulator",
    "AR10-A-E": "regulator",
    # AMC là bộ xả khí (exhaust cleaner), AN là giảm âm. Cùng gắn ở CỬA XẢ và cùng
    # tập cha hợp lệ, nên dùng chung một loại node thay vì thêm nhóm gần trùng.
    "AMC-E": "silencer",
    "AN-E": "silencer",
    "AS-E-E": "speed_controller",
    "AS1-E": "speed_controller",
    "CM2-CDM2-Z-E": "cylinder",
    "CQS-Z-E": "cylinder",
    "MGP-Z-E": "cylinder",
    "D-M9-CM2-E": "sensor",
    "J-E": "joint",
    "JB-E": "joint",
    "KQ2-E": "fitting",
    "TU-E": "tubing",
    "SS5Y-20-E": "manifold",
    "SY-5-E": "valve",
    "SY-E": "valve",
}

# `role` trong bảng tra catalog → loại node. THẮNG bảng series ở trên.
ROLE_NODE_TYPE = {
    "gasket": "manifold_part",
    "end_plate": "manifold_part",
}


def classify(con, code):
    """Mã hàng → loại node. Không chắc thì NÓI KHÔNG BIẾT, không đoán.

    Trả dict luôn có `ok`. Khi ok=False thì có `reason` + `how` để UI hiện được
    ba phần (sai gì · sửa gì · sửa thế nào) như mọi chỗ khác trong engine.
    """
    code = (code or "").strip()
    if not code:
        return {"ok": False, "reason": "chưa gõ mã hàng",
                "how": "Gõ mã như in trên catalog, vd KQ2L06-02NS"}

    r = P.parse(con, code)
    if not r.get("ok"):
        return {"ok": False, "code": code,
                "reason": r.get("error") or "mã không khớp ngữ pháp nào đang có",
                # Không đoán ý mã sai: đoán sai là mua sai hàng (cùng lý lẽ với
                # luật R-PARSE-00). Nhưng phải chừa đường đi tiếp.
                "how": "Kiểm lại mã, hoặc chọn loại thiết bị rồi bật 'Mã tự do' "
                       "để vẫn đưa vào BOM mà không qua kiểm tra kỹ thuật",
                "unparsed": r.get("unparsed")}

    cid = r.get("catalog_id")
    if not cid and r.get("series_id"):
        row = con.execute("select catalog_id from series where id=?",
                          (r["series_id"],)).fetchone()
        cid = row["catalog_id"] if row else None

    role = (r.get("attrs") or {}).get("role")
    nt = ROLE_NODE_TYPE.get(role) or SERIES_NODE_TYPE.get(cid)
    if not nt:
        # Đọc được mã mà chưa biết xếp vào đâu là chuyện KHÁC với mã sai — nói rõ
        # để người dùng biết đây là dữ liệu phần mềm còn thiếu, không phải họ gõ sai.
        return {"ok": False, "code": code, "series": cid,
                "series_name": r.get("series_name"),
                "reason": f"đọc được mã (họ {cid or '?'}) nhưng chưa khai loại "
                          f"thiết bị cho họ này",
                "how": "Chọn loại thiết bị bằng tay lần này; cần thêm một dòng vào "
                       "engine/classify.py SERIES_NODE_TYPE"}

    g = G.GROUPS.get(nt) or {}
    why = (f"{code} thuộc họ {cid}" if not role
           else f"{code} là {role} trong bảng tra của họ {cid}")
    return {"ok": True, "code": code, "node_type": nt,
            "label": g.get("label") or nt, "layer": g.get("layer") or "other",
            "series": cid, "series_name": r.get("series_name"),
            "role": role,
            "allowed_parents": [p for p in T.PARENT_OF.get(nt, ((), ""))[0]],
            "attrs": r.get("attrs") or {},
            "why": why}


def placements(root, nt):
    """Node nào trong cây nhận được thiết bị loại `nt` làm con? Trả [(id, nhãn)].

    Để UI không bắt người dùng tự dò: gõ mã xong, nếu chỗ đang chọn không nhận thì
    hiện thẳng những chỗ nhận được.
    """
    ok_parents = T.PARENT_OF.get(nt, ((), ""))[0]
    out = []
    for n, _, _ in T.walk(root):
        if n.get("type") in ok_parents:
            out.append((n.get("id"),
                        n.get("name") or (G.GROUPS.get(n.get("type")) or {})
                        .get("label") or n.get("type")))
    return out


def gate(con):
    """Cổng G-CLASS-01/02. Trả (đạt, [(tên, đạt, chi tiết)]).

    Chạy trong tests/test_graph.py. Hai điều, và cả hai đều đã suýt sai:
      01 series nào GÕ MÃ VÀO ĐƯỢC (có ngữ pháp) đều phải có loại thiết bị. Thiếu
         thì người dùng gõ mã hợp lệ mà phần mềm nói không biết.
      02 mọi loại khai ở đây phải là nhóm THẬT trong GROUPS, và phải có ít nhất một
         cha hợp lệ trong PARENT_OF — khai một loại không ai nhận làm con thì gõ mã
         xong không gắn được vào đâu.
    """
    have = {r["catalog_id"] for r in con.execute(
        """select distinct s.catalog_id from series s
           join code_slot cs on cs.series_id = s.id where s.catalog_id is not null""")}
    missing = sorted(have - set(SERIES_NODE_TYPE))
    extra = sorted(set(SERIES_NODE_TYPE) - have)
    rep = [("G-CLASS-01-đủ-series", not missing,
            f"{len(have) - len(missing)}/{len(have)} series có ngữ pháp đã khai loại"
            + ("" if not missing else " · THIẾU: " + ", ".join(missing)))]
    bad = []
    for cid, nt in sorted(SERIES_NODE_TYPE.items()):
        if nt not in G.GROUPS:
            bad.append(f"{cid}→{nt} không có trong GROUPS")
        elif not T.PARENT_OF.get(nt, ((), ""))[0]:
            bad.append(f"{cid}→{nt} không có cha hợp lệ nào")
    for role, nt in sorted(ROLE_NODE_TYPE.items()):
        if nt not in G.GROUPS:
            bad.append(f"role {role}→{nt} không có trong GROUPS")
    rep.append(("G-CLASS-02-loại-có-thật", not bad,
                f"{len(SERIES_NODE_TYPE)} series + {len(ROLE_NODE_TYPE)} vai trò"
                + ("" if not bad else " · SAI: " + "; ".join(bad[:3]))))
    if extra:
        # KHÔNG phải lỗi: ngữ pháp có thể chưa nạp vào DB đang dùng (vd DB sạch
        # chưa chạy grammar_seed). Nhưng phải NÓI RA, không im lặng.
        rep.append(("(ghi chú) khai sẵn nhưng DB chưa có ngữ pháp", True,
                    ", ".join(extra)))
    return all(g for _, g, _ in rep), rep
