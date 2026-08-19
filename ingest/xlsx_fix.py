"""Sửa mã hàng sai trong file .xlsx, giữ nguyên mọi thứ khác.

    python3 -m ingest.xlsx_fix BOM/file.xlsx "KQ2L010-02NS" "KQ2L10-02NS"

Cách làm: .xlsx là ZIP chứa XML. Ô text thường nằm trong xl/sharedStrings.xml
(bảng chuỗi dùng chung). Thay đúng chuỗi đó rồi ghi lại ZIP với các entry còn lại
copy nguyên bản — không đụng tới định dạng, công thức, hay sheet nào khác.

LUÔN tạo backup .bak trước khi ghi. Không sửa được thì báo, không ghi file rỗng.
"""
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def patch(path: Path, old: str, new: str, dry_run=False):
    if not path.exists():
        return {"error": f"không có {path}"}

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        blobs = {n: z.read(n) for n in names}

    hits = {n: blobs[n].count(old.encode()) for n in names
            if blobs[n].count(old.encode())}
    if not hits:
        return {"error": f"không tìm thấy '{old}' trong {path.name}"}
    total = sum(hits.values())

    if dry_run:
        return {"dry_run": True, "found": total, "in_files": hits}

    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(path, bak)

    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(path) as zin, \
         zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = blobs[item.filename]
            if item.filename in hits:
                data = data.replace(old.encode(), new.encode())
            # giữ nguyên metadata của từng entry (thời gian, quyền)
            zout.writestr(item, data)
    tmp.replace(path)
    return {"replaced": total, "in_files": hits, "backup": bak.name}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    path, old, new = Path(argv[0]), argv[1], argv[2]
    res = patch(path, old, new, dry_run="--dry-run" in argv)
    print(f"  {path.name}: {res}")
    return 0 if "error" not in res else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
