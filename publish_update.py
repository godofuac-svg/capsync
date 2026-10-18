"""publish_update.py — публикует новую сборку кода CapSync как GitHub Release.
Команда подтянет её сама при следующем запуске (core/selfupdate.py проверяет
GitHub Releases API, exit-code 7 → launch.command/Start.bat подменяют файлы).

Тяжёлое (python/venv, ffmpeg, модель) НЕ трогается и не публикуется — обновляется
только код: run.py, app.py, core/, static/, assets/, BUILD.txt.

  python3 publish_update.py

Требует: gh CLI авторизован (gh auth status), есть права push в репозиторий.
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
APP_FILES = ["run.py", "app.py", "core", "static", "assets", "BUILD.txt"]


def sh(cmd, **kw):
    print("$", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True, **kw)


def main():
    build_file = HERE / "BUILD.txt"
    current = int(build_file.read_text().strip() or "0")
    new_build = current + 1
    build_file.write_text(f"{new_build}\n", encoding="utf-8")
    print(f"сборка {current} → {new_build}")

    work = HERE / "build_update"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    for item in APP_FILES:
        src = HERE / item
        dst = work / item
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, dst)

    zpath = HERE / "app-update.zip"
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(work.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(work))
    print(f"бандл собран: {zpath} ({zpath.stat().st_size / 1e3:.0f} КБ)")

    sh(["git", "add", "BUILD.txt"] + APP_FILES)
    sh(["git", "commit", "-q", "-m", f"build {new_build}"])
    sh(["git", "push"])
    sh(["gh", "release", "create", f"v{new_build}", str(zpath),
        "--title", f"v{new_build}", "--notes", f"Сборка {new_build}"])

    shutil.rmtree(work)
    zpath.unlink()
    print(f"\nОпубликовано: v{new_build}. Команда обновится сама при следующем запуске CapSync.")


if __name__ == "__main__":
    main()
