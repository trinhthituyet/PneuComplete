"""Web UI cho PneuComplete — chỉ dùng stdlib (http.server), không cần FastAPI.

    python3 -m web.server            # http://localhost:8765
    python3 -m web.server --port 9000

Vì sao stdlib: môi trường này không cài được package từ PyPI (bị chặn), mà toàn bộ
project cũng đã theo hướng không phụ thuộc — crawler dùng urllib, đọc xlsx bằng
zipfile, đọc PDF bằng pdftotext. Giữ nguyên hướng đó.

API:
    GET  /                     trang chính
    GET  /api/series           danh sách series có ngữ pháp (để gợi ý nhập)
    GET  /api/parse?code=X     parse 1 mã hàng — kiểm tra ngay khi đang nhập
    POST /api/bom              {inputs, config} → BOM + cảnh báo + gap
    GET  /api/csv?project=N    xuất BOM ra CSV
    GET  /api/defaults         cấu hình mặc định + danh sách khoá cần khai

Cờ dòng lệnh:
    --port N        cổng, mặc định 8765
    --host ADDR     địa chỉ bind. Mặc định 127.0.0.1 = CHỈ máy này truy cập được.
                    Trong Docker phải là 0.0.0.0, nếu không thì host không vào được
                    container (bind 127.0.0.1 bên trong container chỉ nghe loopback
                    CỦA container). Biến môi trường PNEU_HOST cũng đặt được.
"""
import csv
import io
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import db                      # noqa: E402
from engine import bom                      # noqa: E402
from engine import parser as P              # noqa: E402

HERE = Path(__file__).resolve().parent

# Khoá cấu hình engine KHÔNG suy được — UI phải hiển thị rõ để người dùng khai.
# Mỗi khoá kèm nhãn tiếng Việt và lý do, lấy từ rationale của luật tương ứng.
NEEDS_INPUT = [
    ("tube_total_m", "Tổng mét ống cho cả máy",
     "Phụ thuộc layout máy, khoảng cách tủ van tới từng xy-lanh. Engine không suy được."),
    ("main_line_port_size", "Cỡ cửa đường trục chính (FRL)",
     "Cỡ FRL theo tổng lưu lượng, nhưng catalog chỉ cho lưu lượng dạng đồ thị."),
    ("frl_size", "Cỡ AC (10/20/25/30/40)",
     "Một cỡ cửa có ở nhiều cỡ AC — engine liệt kê ứng viên, bạn chọn."),
    ("valve_series_size", "Cỡ van (SY3000/SY5000/SY7000)",
     "Phụ thuộc lưu lượng cần thiết; engine chưa trích được Cv từ catalog."),
    ("valve_function", "Loại van mặc định",
     "Phụ thuộc CHỨC NĂNG từng cơ cấu — khai riêng cho từng xy-lanh ở bảng bên trên."),
    ("manifold_type", "Kiểu manifold",
     "Type 20 và Type 20P dùng end plate khác nhau; chọn sai thì không lắp được."),
]


def api_series(con):
    rows = con.execute(
        """select s.id, s.code, s.catalog_id, s.name, s.part_prefix,
                  (select count(*) from code_slot cs where cs.series_id=s.id) slots
           from series s
           where exists (select 1 from code_slot cs where cs.series_id=s.id)
           order by s.code""").fetchall()
    return [dict(r) for r in rows]


def api_parse(con, code):
    if not code:
        return {"ok": False, "error": "thiếu mã"}
    r = P.parse(con, code)
    return {"ok": bool(r.get("ok")), "series": r.get("series"),
            "series_name": r.get("series_name"), "attrs": r.get("attrs"),
            "trace": [{"slot": t[0], "code": t[1], "label": t[2]} for t in r.get("trace", [])],
            "unparsed": r.get("unparsed"), "missing": r.get("missing"),
            "error": r.get("error")}


def api_bom(con, payload):
    inputs = []
    for it in payload.get("inputs", []):
        code = (it.get("code") or "").strip()
        if not code:
            continue
        qty = int(it.get("qty") or 1)
        over = {k: v for k, v in (it.get("overrides") or {}).items()
                if v not in (None, "", "auto")}
        inputs.append((code, qty, over))
    if not inputs:
        return {"error": "chưa nhập actuator nào"}

    cfg = {}
    for k, v in (payload.get("config") or {}).items():
        if v in (None, "", "auto"):
            continue
        if k in ("tube_total_m", "tube_od_mm", "tube_roll_length_m",
                 "pressure_mpa", "cycle_s", "safety_factor"):
            cfg[k] = float(v)
        elif k in ("use_manifold", "frl_lubricator", "frl_mist_separator", "automation"):
            cfg[k] = v in (True, "true", "1", "co", "có")
        else:
            cfg[k] = v

    bom.seed_rules(con)
    res = bom.build(con, inputs, cfg, project_name=payload.get("name") or "web")
    return {
        "project_id": res["project_id"],
        "project": {k: v for k, v in res["project"].items()},
        "calc": res["calc"], "system": res["system"],
        "lines": res["lines"], "warnings": res["warnings"], "gaps": res["gaps"],
    }


def api_csv(con, project_id):
    rows = con.execute(
        """select po.layer, po.proposed_code, po.qty, po.rule_code, po.rationale,
                  po.confidence, po.status
           from project_output po where po.project_id=? order by po.layer, po.id""",
        (project_id,)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Tầng", "Mã hàng", "Số lượng", "Luật", "Độ tin cậy", "Trạng thái", "Lý do"])
    for r in rows:
        w.writerow([r["layer"], r["proposed_code"] or "", r["qty"], r["rule_code"] or "",
                    f"{r['confidence']:.0%}" if r["confidence"] else "",
                    r["status"], (r["rationale"] or "").replace("\n", " ")])
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "PneuComplete/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str)
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        con = db.connect()
        try:
            if u.path in ("/", "/index.html"):
                self._send(200, (HERE / "index.html").read_bytes(),
                           "text/html; charset=utf-8")
            elif u.path == "/api/series":
                self._send(200, api_series(con))
            elif u.path == "/api/defaults":
                self._send(200, {"defaults": bom.DEFAULT_PROJECT,
                                 "needs_input": [{"key": k, "label": l, "why": w}
                                                 for k, l, w in NEEDS_INPUT],
                                 "valve_functions": list(bom.VALVE_FUNCTION)})
            elif u.path == "/api/parse":
                self._send(200, api_parse(con, (q.get("code") or [""])[0]))
            elif u.path == "/api/csv":
                pid = int((q.get("project") or ["0"])[0])
                self._send(200, api_csv(con, pid), "text/csv; charset=utf-8")
            else:
                self._send(404, {"error": "không có đường dẫn này"})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            con.close()

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        con = db.connect()
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
            if u.path == "/api/bom":
                self._send(200, api_bom(con, payload))
            else:
                self._send(404, {"error": "không có đường dẫn này"})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            con.close()


def main(argv):
    port = int(os.environ.get("PNEU_PORT") or 8765)
    host = os.environ.get("PNEU_HOST") or "127.0.0.1"
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--host" in argv:
        host = argv[argv.index("--host") + 1]
    srv = ThreadingHTTPServer((host, port), Handler)
    where = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"PneuComplete UI → http://{where}:{port}   (bind {host})")
    print("  Ctrl-C để dừng")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ndừng")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
