import os, json
from pathlib import Path

APP_NAME = "GREENADVISE"

def _config_path() -> Path:
    # Windows: %APPDATA%\GREENADVISE\config.json ; otherwise: ~/.GREENADVISE/config.json
    base = os.environ.get("APPDATA") or str(Path.home())
    folder = Path(base) / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "config.json"

def _load_config() -> dict:
    p = _config_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg = {"ninja_api_key": ""}
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg

def get_ninja_api_key() -> str:
    env_key = os.getenv("RENEWABLES_NINJA_API_KEY")
    if env_key:
        return env_key.strip()
    return (_load_config().get("ninja_api_key") or "").strip()


def save_ninja_api_key(key: str) -> None:
    p = _config_path()
    try:
        cfg = _load_config()
    except Exception:
        cfg = {}
    cfg["ninja_api_key"] = key.strip()
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
