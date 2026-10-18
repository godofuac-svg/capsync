"""
align_client.py — родительская сторона протокола к align_worker_proc.py.

Держит один живой сабпроцесс на всю сессию обработки очереди (модель
грузится один раз и переиспользуется между задачами). stop() убивает
процесс мгновенно — для кнопки «Стоп», которая должна рвать работу
«в ту же секунду», а не ждать кооперативной проверки флага.
"""
import json
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent / "align_worker_proc.py"


class Cancelled(Exception):
    pass


class AlignClient:
    def __init__(self, python_exe: str):
        self._python_exe = python_exe
        self._proc: subprocess.Popen | None = None

    def ensure_started(self):
        if self._proc is not None and self._proc.poll() is None:
            return
        self._proc = subprocess.Popen(
            [self._python_exe, str(_SCRIPT)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def stop(self):
        if self._proc is None:
            return
        try:
            self._proc.kill()
        except Exception:
            pass
        self._proc = None

    def request(self, req: dict, on_progress=None):
        """Отправляет запрос и читает построчно, пока не придёт result/error.
        Бросает Cancelled, если процесс умер (убит stop()) до результата."""
        self.ensure_started()
        proc = self._proc
        proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        proc.stdin.flush()

        while True:
            line = proc.stdout.readline()
            if line == "":
                # EOF — процесс умер (либо убит stop(), либо упал сам)
                stderr_tail = ""
                try:
                    stderr_tail = proc.stderr.read()
                except Exception:
                    pass
                self._proc = None
                raise Cancelled(stderr_tail or "align-процесс завершился без ответа")
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg["type"] == "progress":
                if on_progress:
                    on_progress(msg["message"])
                continue
            if msg["type"] == "result":
                return msg["data"]
            if msg["type"] == "error":
                raise RuntimeError(msg["message"] + "\n\n" + msg.get("traceback", ""))
