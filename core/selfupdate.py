"""
selfupdate.py — лёгкое автообновление кода (не тяжёлых частей). Тот же паттерн,
что у FMBT-воркера (exit-code 7 → launch.command/Start.bat подменяет файлы и
перезапускает), но без SSH-туннеля и лицензионного ключа — репозиторий публичный,
обновления через обычный GitHub Releases API. Тяжёлое (python/, ffmpeg/, модель)
не трогается — только run.py/app.py/core/static/assets/BUILD.txt.

Любой сбой (нет сети, репо недоступен) — работаем на текущей версии, никого не
блокируем, НО теперь громко пишем в консоль почему — раньше это было полностью
тихо (ни единого print), и когда self-update реально падал (например, из-за
сетевой ошибки), человек не понимал, почему обновление "не докатилось".
"""
import json
import shutil
import sys
import tempfile
import time
import traceback
import urllib.request
import zipfile
from pathlib import Path

REPO = "godofuac-svg/capsync"
ROOT = Path(__file__).parent.parent
APP_NEW_DIR = ROOT / "app_new"


def _log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] [selfupdate] {msg}", flush=True)


def local_build() -> int:
    f = ROOT / "BUILD.txt"
    try:
        return int(f.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def check_and_apply() -> bool:
    """True, если скачано обновление и в app_new/ лежит новая версия — тогда
    вызывающий код должен сделать sys.exit(7), чтобы launch.command/Start.bat её применили."""
    local = local_build()
    _log(f"проверяется обновление (текущая сборка: {local})…")
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())

        tag = data.get("tag_name", "v0").lstrip("v")
        remote_build = int(tag)
        _log(f"последняя сборка на GitHub: {remote_build}")
        if remote_build <= local:
            _log("обновлений нет — работаю на текущей версии")
            return False

        asset = next((a for a in data.get("assets", []) if a["name"] == "app-update.zip"), None)
        if asset is None:
            _log(f"ВНИМАНИЕ: в релизе v{remote_build} нет файла app-update.zip — "
                 f"пропускаю обновление (это баг публикации на GitHub, не у тебя)")
            return False

        _log(f"скачивается сборка {remote_build} ({asset.get('size', 0) / 1024:.0f} КБ)…")
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
            _log("ВНИМАНИЕ: скачанный архив битый (нет BUILD.txt внутри) — пропускаю обновление")
            shutil.rmtree(APP_NEW_DIR, ignore_errors=True)
            return False

        _log(f"сборка {remote_build} распакована в app_new/ — перезапускаюсь, чтобы применить")
        return True
    except Exception as e:
        _log(f"ОШИБКА проверки обновления (работаю дальше на текущей версии): {e}")
        _log(traceback.format_exc())
        return False


if __name__ == "__main__":
    # вызывается из run.py ДО старта сервера; код возврата 7 — сигнал для
    # launch.command/Start.bat подменить файлы и перезапустить
    sys.exit(7 if check_and_apply() else 0)
