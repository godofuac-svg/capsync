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
    """Процесс убит НАМЕРЕННО (кнопка «Стоп») — это не ошибка, ничего в консоль
    про это печатать как про краш не нужно."""
    pass


class AlignClient:
    def __init__(self, python_exe: str):
        self._python_exe = python_exe
        self._proc: subprocess.Popen | None = None
        self._stopped_intentionally = False

    def ensure_started(self):
        if self._proc is not None and self._proc.poll() is None:
            return
        self._stopped_intentionally = False
        self._proc = subprocess.Popen(
            [self._python_exe, str(_SCRIPT)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def stop(self):
        if self._proc is None:
            return
        self._stopped_intentionally = True
        try:
            self._proc.kill()
        except Exception:
            pass
        self._proc = None

    def request(self, req: dict, on_progress=None):
        """Отправляет запрос и читает построчно, пока не придёт result/error.
        Бросает Cancelled, если процесс убит через stop() (кнопка «Стоп») — это не
        ошибка. Если процесс умер САМ (упал/крашнулся) — бросает RuntimeError с
        хвостом его stderr, чтобы настоящая причина не терялась под "остановлено"."""
        self.ensure_started()
        proc = self._proc
        proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        proc.stdin.flush()

        while True:
            line = proc.stdout.readline()
            if line == "":
                # EOF — процесс закончился без ответа: либо мы его убили (stop()),
                # либо он упал сам — это два РАЗНЫХ случая, путать их нельзя
                stderr_tail = ""
                try:
                    stderr_tail = proc.stderr.read()
                except Exception:
                    pass
                was_intentional = self._stopped_intentionally
                proc.wait()  # без этого returncode ещё может быть не выставлен
                rc = proc.returncode
                self._proc = None
                if was_intentional:
                    raise Cancelled("остановлено пользователем")
                raise RuntimeError(
                    f"align-процесс неожиданно завершился (код {rc}).\n"
                    f"stderr процесса:\n{stderr_tail or '(пусто)'}")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                # какая-то библиотека напечатала что-то в stdout мимо нашего протокола —
                # не роняем всю задачу из-за постороннего предупреждения, просто показываем,
                # что именно это было, и читаем дальше
                if on_progress:
                    on_progress(f"(из align-процесса, не по протоколу): {line}")
                continue
            if msg["type"] == "progress":
                if on_progress:
                    on_progress(msg["message"])
                continue
            if msg["type"] == "result":
                return msg["data"]
            if msg["type"] == "error":
                raise RuntimeError(msg["message"] + "\n\n" + msg.get("traceback", ""))
