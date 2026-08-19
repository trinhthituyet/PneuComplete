"""Cho test dùng bản DB TẠM, không ghi vào pneu.db thật của người dùng.

VÌ SAO CẦN: `bom.build()` ghi một dòng `project` + các dòng output/warning mỗi
lần chạy. Bộ test gọi nó hàng chục lần, mỗi lần chạy test lại cộng thêm — đây là
nguồn chính của 380 nghìn dòng rác tìm thấy trong pneu.db trên máy phát triển.
Dọn theo hạn mức (bom.PROJECT_KEEP) chặn được phần phình, nhưng test vẫn không
nên chạm vào dữ liệu thật: nó làm mất phương án của người dùng khỏi hạn mức đó.

CÁCH DÙNG — phải import TRƯỚC `from crawler import db`:

    import tmpdb                              # noqa: F401  (phải đứng trước)
    from crawler import db

Lý do thứ tự quan trọng: `db.DB_PATH` đọc biến môi trường PNEU_DB MỘT LẦN lúc
import module. Import sau thì đã muộn, test sẽ ghi vào DB thật.
"""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "pneu.db"


def _setup() -> str:
    # Đã có ai đặt PNEU_DB (ví dụ test cha gọi test con) thì tôn trọng, không
    # tạo thêm bản tạm lồng nhau.
    if os.environ.get("PNEU_DB"):
        return os.environ["PNEU_DB"]

    fd, path = tempfile.mkstemp(prefix="pneu-test-", suffix=".db")
    os.close(fd)
    if REAL.exists():
        shutil.copy2(REAL, path)
    os.environ["PNEU_DB"] = path

    @atexit.register
    def _cleanup():
        # WAL/shm sinh ra cạnh DB, xoá luôn kẻo rác lại /tmp.
        for p in (path, path + "-wal", path + "-shm"):
            try:
                os.remove(p)
            except OSError:
                pass

    return path


PATH = _setup()
