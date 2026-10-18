"""
launch_windows.py — тонкий запускатель CapSync под Windows (аналог launch.command
на Mac). Компилируется в CapSync.exe через PyInstaller (см. BUILD.md) — сам exe
ничего тяжёлого не содержит, он только находит/готовит venv и запускает run.py.
Тяжёлые зависимости (faster-whisper/stable-ts/ffmpeg) и модель распознавания
ставит сам CapSync на экране первого запуска (core/setup.py) — иначе лончер
висел бы с пустым окном консоли по 10+ минут при первом клике.

Лежит РЯДОМ с run.py/requirements-bootstrap.txt (то есть в корне capsync/) —
venv создаётся тут же, в .venv/.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).parent).resolve()
# _MEIPASS — временная папка распакованного PyInstaller-бинаря; сам .venv и run.py
# должны лежать РЯДОМ с exe-файлом на диске, а не внутри него, поэтому для venv/run.py
# берём папку, где лежит сам .exe, а не _MEIPASS
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
APP_DIR = APP_DIR.resolve()

VENV_DIR = APP_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"

CANDIDATE_VERSIONS = ["3.11", "3.12", "3.10"]  # те же версии, что и в launch.command на Mac —
# у более новых (3.14/3.15) часто ещё нет готовых wheel-ов под ctranslate2/av, сборка из
# исходников на машине без compiler toolchain просто упадёт


def _pause_and_exit(code=1):
    input("\n(нажми Enter, чтобы закрыть окно)")
    sys.exit(code)


def find_python() -> str:
    """Ищет подходящую версию Python через `py -X.Y` (стандартный Windows launcher)."""
    for ver in CANDIDATE_VERSIONS:
        try:
            out = subprocess.run(["py", f"-{ver}", "--version"], capture_output=True, text=True)
            if out.returncode == 0:
                print(f"▸ использую Python {ver} ({out.stdout.strip() or out.stderr.strip()})")
                return f"-{ver}"
        except FileNotFoundError:
            break  # нет самого `py` launcher-а вообще
    return ""


def main():
    print("===============================================")
    print("  CapSync — FMB Team")
    print("===============================================")

    if not VENV_PYTHON.is_file():
        print("▸ первый запуск: создаю окружение…")
        py_flag = find_python()
        if not py_flag:
            print("✗ Не найден подходящий Python (3.10–3.12).")
            print("  Поставь с https://python.org/downloads/ (отметь \"Add to PATH\" при установке),")
            print("  потом запусти CapSync.exe снова.")
            _pause_and_exit()
        res = subprocess.run(["py", py_flag, "-m", "venv", str(VENV_DIR)])
        if res.returncode != 0:
            print("✗ не удалось создать venv")
            _pause_and_exit()
        subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-q", "--upgrade", "pip"])

    # лёгкие зависимости — синхронизируем КАЖДЫЙ запуск (venv может быть старым, см.
    # комментарий в launch.command — ровно тот же баг здесь воспроизводим одинаково)
    req = APP_DIR / "requirements-bootstrap.txt"
    res = subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-q", "-r", str(req)])
    if res.returncode != 0:
        print("✗ pip install упал (см. вывод выше)")
        _pause_and_exit()

    print("▸ запускаю CapSync…")
    run_py = APP_DIR / "run.py"
    os.chdir(APP_DIR)
    res = subprocess.run([str(VENV_PYTHON), str(run_py)])
    if res.returncode != 0:
        _pause_and_exit(res.returncode)


if __name__ == "__main__":
    main()
