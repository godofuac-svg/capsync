"""
selfupdate.py — лёгкое автообновление кода (не тяжёлых частей). Тот же паттерн,
что у FMBT-воркера (exit-code 7 → launch.command/Start.bat подменяет файлы и
перезапускает), но без SSH-туннеля и лицензионного ключа — репозиторий публичный,
обновления через обычный GitHub Releases API. Тяжёлое (python/, ffmpeg/, модель)
не трогается — только run.py/app.py/core/static/assets/BUILD.txt.

Любой сбой (нет сети, репо недоступен) — молча работаем на текущей версии,
никого не блокируем.
"""
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "godofuac-svg/capsync"
ROOT = Path(__file__).parent.parent
APP_NEW_DIR = ROOT / "app_new"


def local_build() -> int:
    f = ROOT / "BUILD.txt"
    try:
        return int(f.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def check_and_apply() -> bool:
    """True, если скачано обновление и в app_new/ лежит новая версия — тогда
    вызывающий код должен сделать sys.exit(7), чтобы launch.command/Start.bat её применили."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())

        tag = data.get("tag_name", "v0").lstrip("v")
        remote_build = int(tag)
        if remote_build <= local_build():
            return False

        asset = next((a for a in data.get("assets", []) if a["name"] == "app-update.zip"), None)
        if asset is None:
            return False

        with urllib.request.urlopen(asset["browser_download_url"], timeout=120) as r:
            blob = r.read()

        tmpzip = Path(tempfile.gettempdir()) / "capsync_update.zip"
        tmpzip.write_bytes(blob)

        if APP_NEW_DIR.exists():
            shutil.rmtree(APP_NEW_DIR, ignore_errors=True)
        with zipfile.ZipFile(tmpzip) as z:
            z.extractall(APP_NEW_DIR)
        tmpzip.unlink(missing_ok=True)

        if not (APP_NEW_DIR / "BUILD.txt").is_file():
            shutil.rmtree(APP_NEW_DIR, ignore_errors=True)
            return False

        return True
    except Exception:
        return False


if __name__ == "__main__":
    # вызывается из run.py ДО старта сервера; код возврата 7 — сигнал для
    # launch.command/Start.bat подменить файлы и перезапустить
    sys.exit(7 if check_and_apply() else 0)
