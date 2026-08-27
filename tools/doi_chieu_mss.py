"""So số của engine với số đọc từ Model Selection Software của SMC.

    python3 tools/doi_chieu_mss.py              # xem đã kiểm được bao nhiêu
    python3 tools/doi_chieu_mss.py --doi-chung  # đối chứng âm: cố ý nhập sai

Bạn đăng nhập mssc.smcworld.com bằng tay, điền số vào `mss:` trong
db/seed/_doi-chieu-mss.yaml, rồi chạy lệnh này.

Ô CHƯA ĐIỀN = CHƯA KIỂM, KHÔNG PHẢI ĐẠT. Đây là chỗ cổng kiểu này thường mục ruỗng:
để trống hết mà báo "0 lệch · ĐẠT" thì mọi người tưởng đã đối chiếu xong. Nên lệnh
này luôn in số ca CHỜ và trả mã khác 0 khi còn ca chờ.

VÌ SAO ENGINE ĐỌC ĐƯỢC SỐ NÀY MÀ TÔI KHÔNG TỰ LẤY: xem
docs/smc-selection-software.md — host mssc.smcworld.com bị chặn ở tầng mạng, trang
đăng nhập trả 403 cho UA trung thực, và công cụ là ứng dụng một trang cần
JavaScript. Ba thứ đó không sửa được bằng việc có tài khoản.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml                                    # noqa: E402

SRC = ROOT / "db/seed/_doi-chieu-mss.yaml"

# (khoá trong YAML, tên hiển thị, [(khoá engine, khoá mss, loại sai số)])
NHOM = [
    ("co_ac", "Cỡ AC theo lưu lượng (acmss)",
     [("co", "co", "co"), ("ap_ra_mpa", "ap_ra_mpa", "ap_mpa")]),
    ("dan_nap_am_van", "Dẫn nạp âm C của van (fccs)",
     [("C", "C", "luu_luong_pc"),
      ("luu_luong_lpm_tai_0_5mpa", "luu_luong_lpm", "luu_luong_pc")]),
    ("luu_luong_tieu_thu", "Lưu lượng tiêu thụ (accs)",
     [("L_moi_chu_ky", "L_moi_chu_ky", "luu_luong_pc"),
      ("lpm", "lpm", "luu_luong_pc")]),
]


def lech(kind, a, b, tol):
    """Trả (có_lệch, mô tả). `a` = engine, `b` = MSS."""
    if kind == "co":
        return (str(a) != str(b), f"{a} vs {b}")
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return (True, f"không so được: {a!r} vs {b!r}")
    if kind == "ap_mpa":
        d = abs(a - b)
        return (d > tol["ap_mpa"], f"{a:g} vs {b:g} (lệch {d:.3f} MPa)")
    d = abs(a - b) / max(abs(b), 1e-9) * 100
    return (d > tol["luu_luong_pc"], f"{a:g} vs {b:g} (lệch {d:.1f}%)")


def run(doc):
    tol = doc["sai_so"]
    n_ok = n_bad = n_cho = 0
    bad = []
    for key, ten, fields in NHOM:
        print(f"\n── {ten}")
        for ca in doc.get(key) or []:
            nhap = " · ".join(f"{k}={v}" for k, v in ca["nhap"].items())
            mss = ca.get("mss") or {}
            if all(mss.get(mk) is None for _, mk, _ in fields):
                n_cho += 1
                print(f"   CHỜ   {nhap[:76]}")
                continue
            hong = []
            for ek, mk, kind in fields:
                if mss.get(mk) is None:
                    continue
                is_bad, desc = lech(kind, (ca["engine"] or {}).get(ek), mss[mk], tol)
                hong.append((is_bad, f"{ek}: {desc}"))
            if any(b for b, _ in hong):
                n_bad += 1
                bad.append((ten, nhap, [d for b, d in hong if b]))
                print(f"   LỆCH  {nhap[:76]}")
                for b, d in hong:
                    print(f"           {'✗' if b else '✓'} {d}")
            else:
                n_ok += 1
                print(f"   KHỚP  {nhap[:76]}")
                for _, d in hong:
                    print(f"           ✓ {d}")
    return n_ok, n_bad, n_cho, bad


def main(argv):
    doc = yaml.safe_load(SRC.read_text())
    if "--doi-chung" in argv:
        # ĐỐI CHỨNG ÂM: một cổng không thể BÁO LỆCH thì không phải cổng. Nhồi số
        # sai vào ca đầu của mỗi nhóm rồi đòi phát hiện đúng số đó.
        print("ĐỐI CHỨNG ÂM — cố ý nhập sai, phải bị bắt hết")
        seeded = 0
        for key, _, fields in NHOM:
            ca = (doc.get(key) or [None])[0]
            if not ca:
                continue
            ca["mss"] = {}
            for ek, mk, kind in fields:
                v = (ca["engine"] or {}).get(ek)
                if v is None:
                    continue
                ca["mss"][mk] = "99" if kind == "co" else float(v) * 2 + 1
            seeded += 1
        _, n_bad, _, _ = run(doc)
        print(f"\n{n_bad}/{seeded} ca sai bị bắt")
        if n_bad != seeded:
            print("✗ ĐỐI CHỨNG ÂM THẤT BẠI: có ca sai KHÔNG bị bắt → phép so vô dụng")
            return 1
        print("✓ mọi ca sai đều bị bắt")
        return 0

    print(f"Đối chiếu engine ↔ MSS   (nguồn: {doc.get('nguon')})")
    print(f"người kiểm: {doc.get('nguoi_kiem') or '—'} · "
          f"ngày: {doc.get('ngay_kiem') or '—'}")
    n_ok, n_bad, n_cho, bad = run(doc)
    print("\n" + "=" * 62)
    print(f"{n_ok} khớp · {n_bad} LỆCH · {n_cho} chờ bạn đọc số từ MSS")
    if bad:
        print("\nCÁC CHỖ LỆCH — phải giải thích được, không sửa số cho khớp:")
        for ten, nhap, ds in bad:
            print(f"  {ten}: {nhap[:60]}")
            for d in ds:
                print(f"     {d}")
        return 1
    if n_cho:
        print("\nCHƯA ĐỦ ĐỂ KẾT LUẬN: còn ô `mss:` để trống. Trống KHÔNG phải là đạt.")
        return 2
    print("\n✓ mọi ca đã đối chiếu và khớp")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
