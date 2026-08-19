"""Đọc tệp cấu hình (luật, template giao diện) — không phụ thuộc PyYAML.

VÌ SAO TỒN TẠI: `import yaml` (PyYAML) KHÔNG có trong stdlib Python. Máy người
dùng cuối thường không có nó, và engine gọi tới nó ở đường chạy chính:
  · engine/bom.py       seed_rules()     đọc db/seed/rules.yaml
  · engine/materialize.py load_templates() đọc db/seed/interfaces.yaml
Thiếu PyYAML là phần mềm vỡ ngay với ModuleNotFoundError — không phải lỗi người
dùng hiểu được.

CÁCH GIẢI (chốt: đóng gói bằng Docker): ảnh Docker đã cài PyYAML sẵn, nên YAML là
định dạng DUY NHẤT lúc chạy — không cần bản .json song song, không sợ hai bản lệch
nhau. Đây là lý do chính để chọn Docker: nó biến phụ thuộc thành việc của người
đóng gói, không phải của người dùng.

Vẫn giữ nhánh đọc .json làm phương án dự phòng cho trường hợp chạy TRỰC TIẾP bằng
Python trên máy không có PyYAML (xem tools/package.py --json-only).

Thứ tự thử: PyYAML đọc .yaml → .json nếu có → báo lỗi rõ ràng bằng tiếng Việt.
"""
import json
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def load(path) -> object:
    """Đọc tệp cấu hình. Ưu tiên .yaml (bản gốc), rơi về .json nếu thiếu PyYAML."""
    p = Path(path)
    js = p.with_suffix(".json")

    if p.exists():
        try:
            import yaml
        except ModuleNotFoundError:
            if js.exists():
                return json.loads(js.read_text(encoding="utf-8"))
            raise ConfigError(
                f"Máy chưa cài PyYAML nên không đọc được {p.name}.\n"
                f"  · Cách chuẩn: chạy phần mềm bằng Docker "
                f"(nháy đúp PneuComplete-Docker.command) — ảnh Docker đã có PyYAML.\n"
                f"  · Hoặc cài trực tiếp: pip3 install pyyaml\n"
                f"  · Hoặc sinh bản .json: python3 tools/package.py --json-only"
            ) from None
        return yaml.safe_load(p.read_text(encoding="utf-8"))

    if js.exists():
        return json.loads(js.read_text(encoding="utf-8"))

    raise ConfigError(f"Không tìm thấy {p} lẫn {js}")


def dump_json(path) -> Path:
    """Chuyển một .yaml thành .json cạnh nó (dùng khi đóng gói)."""
    import yaml
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    js = p.with_suffix(".json")
    js.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return js
