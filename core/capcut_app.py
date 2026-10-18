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
    """Закрывает CapCut (сначала мягко, затем принудительно). True, если после вызова не бежит."""
    procs = running_processes()
    if not procs:
        return True
    # на маке процессов несколько (хелперы GPU/renderer/crash handler) — трогаем только
    # главный, хелперы завершатся сами вслед за ним; на всякий случай terminate() всем совпавшим
    for p in procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_running():
            return True
        time.sleep(0.3)

    # не закрылось мягко — добиваем
    for p in running_processes():
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.5)
    return not is_running()


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
            return False
    except Exception:
        pass
    return False
