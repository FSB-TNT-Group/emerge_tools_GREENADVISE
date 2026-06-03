from pathlib import Path
import os, json

APP_NAME = "GREENADVISE"
base = os.environ.get("APPDATA") or str(Path.home())
folder = Path(base) / APP_NAME
folder.mkdir(parents=True, exist_ok=True)

config_file = folder / "config.json"
if not config_file.exists():
    config_file.write_text('{"ninja_api_key": ""}', encoding="utf-8")

print("Config file created/opened at:")
print(config_file)
