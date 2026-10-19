"""
capcut_app.py — автоматически закрывает CapCut перед записью в его файлы
проектов (root_meta_info.json читается/пишется самим CapCut, если он открыт
одновременно с нами — гонка записи может затереть один из черновиков) и
открывает обратно, когда очередь задач обработана.
"""
import platform
import shutil
import subprocess
import time

import psutil

OS_NAME = platform.system()


def _log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] [capcut_app] {msg}", flush=True)

_PROC_MATCH = {
    "Darwin": ("CapCut.app/Contents/MacOS/CapCut",),
    "Windows": ("CapCut.exe",),
}


def _matches(proc: psutil.Process) -> bool:
    try:
        exe = proc.exe() or ""
    except (psutil.AccessDenied, psutil.ZombieProcess, psutil.NoSuchProcess):
        exe = ""
    try:
        name = proc.name() or ""
    except (psutil.AccessDenied, psutil.ZombieProcess, psutil.NoSuchProcess):
        name = ""
    for needle in _PROC_MATCH.get(OS_NAME, ()):
        if needle in exe or needle == name:
            return True
    return False


def running_processes() -> list[psutil.Process]:
    out = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if _matches(proc):
                out.append(proc)
        except (psutil.AccessDenied, psutil.ZombieProcess, psutil.NoSuchProcess):
            continue
    return out


def is_running() -> bool:
    return len(running_processes()) > 0


def close(timeout: float = 12.0) -> bool:
    """Закрывает CapCut (сначала мягко, затем принудительно). True, если после вызова не бежит.
    ВАЖНО: вызывающий код (worker.py) обязан проверять результат — вся защита от гонки
    записи в root_meta_info.json строится на том, что CapCut реально закрыт к этому моменту."""
    procs = running_processes()
    if not procs:
        return True
    _log(f"найдено {len(procs)} процесс(ов) CapCut — закрываю мягко…")
    # на маке процессов несколько (хелперы GPU/renderer/crash handler) — трогаем только
    # главный, хелперы завершатся сами вслед за ним; на всякий случай terminate() всем совпавшим
    for p in procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            _log(f"не удалось мягко завершить процесс {p.pid}: {e}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_running():
            _log("CapCut закрыт")
            return True
        time.sleep(0.3)

    # не закрылось мягко — добиваем
    _log(f"не закрылся за {timeout}с — добиваю принудительно…")
    for p in running_processes():
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            _log(f"не удалось принудительно завершить процесс {p.pid}: {e}")
    time.sleep(0.5)
    ok = not is_running()
    _log("CapCut закрыт" if ok else "CapCut НЕ закрылся — возможна гонка записи файлов проектов")
    return ok


def reopen() -> bool:
    try:
        if OS_NAME == "Darwin":
            subprocess.Popen(["open", "-a", "CapCut"])
            return True
        if OS_NAME == "Windows":
            exe = shutil.which("CapCut.exe")
            if not exe:
                import os
                for base in (
                    os.environ.get("ProgramFiles", r"C:\Program Files"),
                    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                    os.environ.get("LOCALAPPDATA", ""),
                ):
                    cand = os.path.join(base, "CapCut", "CapCut.exe")
                    if os.path.isfile(cand):
                        exe = cand
                        break
            if exe:
                subprocess.Popen([exe])
                return True
            _log("CapCut.exe не найден ни в PATH, ни в Program Files/LOCALAPPDATA — "
                 "открой его вручную, автозапуск не сработал")
            return False
        _log(f"переоткрытие не реализовано для ОС {OS_NAME!r}")
        return False
    except Exception as e:
        _log(f"ошибка при попытке переоткрыть CapCut: {e}")
        return False
