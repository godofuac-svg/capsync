"""
worker.py — очередь задач CapSync: фоновый поток, который по очереди гоняет
задачи через align_client (forced alignment) и capcut_inject (сборка
проекта), публикует состояние для /api/state и умеет мгновенно остановиться.
"""
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from . import align_client, capcut_app, capcut_inject, osdetect, settings as settings_mod

_ROOT = Path(__file__).parent.parent


def _log(msg: str):
    """Единственный канал диагностики — консоль, в которой и так открыт CapSync
    (Start.bat/launch.command не прячут окно терминала). Никаких лог-файлов и
    диалогов сохранения — человек просто выделяет весь вывод терминала и шлёт его."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Worker:
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: list[dict] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._progress = {"task_index": 0, "total": 0, "percent": 0, "message": ""}
        self._last_error: dict | None = None
        self._align = align_client.AlignClient(sys.executable)

    # ---------- публичное API, вызывается из FastAPI-роутов ----------

    def add_task(self, text: str, audio_path: str, project_name: str | None, language: str) -> str:
        task_id = uuid.uuid4().hex[:10]
        with self._lock:
            self._tasks.append({
                "id": task_id, "text": text, "audio_path": audio_path,
                "audio_filename": Path(audio_path).name, "project_name": project_name,
                "language": language, "status": "queued", "step": "", "error": None,
            })
        return task_id

    def clear_finished(self):
        with self._lock:
            if self._running:
                return
            self._tasks = [t for t in self._tasks if t["status"] == "queued"]
            self._last_error = None
            self._progress = {"task_index": 0, "total": 0, "percent": 0, "message": ""}

    def remove_task(self, task_id: str) -> bool:
        with self._lock:
            for t in self._tasks:
                if t["id"] == task_id and t["status"] == "queued":
                    self._tasks.remove(t)
                    return True
        return False

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(self):
        with self._lock:
            if self._running:
                return
            if not any(t["status"] == "queued" for t in self._tasks):
                return
            self._running = True
            self._stop_event.clear()
            self._last_error = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._align.stop()  # убивает align-сабпроцесс мгновенно, если тот сейчас считает

    def state(self) -> dict:
        with self._lock:
            cfg = settings_mod.load()
            folder = cfg["capcut_folder"] or (str(osdetect.autodetect()) if osdetect.autodetect() else None)
            found = bool(folder and osdetect.is_valid_draft_root(Path(folder)))
            return {
                "running": self._running,
                "tasks": list(self._tasks),
                "progress": dict(self._progress),
                "last_error": self._last_error,
                "capcut": {
                    "os": osdetect.os_label(),
                    "folder": folder,
                    "found": found,
                    "instructions": None if found else osdetect.instructions_text(),
                },
                "settings": cfg,
            }

    # ---------- внутреннее ----------

    def _set_progress(self, idx, total, message, percent=None):
        with self._lock:
            self._progress = {
                "task_index": idx, "total": total,
                "percent": percent if percent is not None else self._progress.get("percent", 0),
                "message": message,
            }

    def _set_task_status(self, task_id, **fields):
        with self._lock:
            for t in self._tasks:
                if t["id"] == task_id:
                    t.update(fields)
                    break

    def _run(self):
        cfg = settings_mod.load()
        draft_root = Path(cfg["capcut_folder"]) if cfg["capcut_folder"] else osdetect.autodetect()

        _log("=== запускается очередь ===")
        self._set_progress(0, 0, "Проверяется, не открыт ли CapCut…")
        _log("проверяется, не открыт ли CapCut…")
        capcut_app.close()

        with self._lock:
            queued = [t for t in self._tasks if t["status"] == "queued"]
        total = len(queued)
        _log(f"задач в очереди: {total}")

        stopped = False
        try:
            for idx, task in enumerate(queued, start=1):
                if self._stop_event.is_set():
                    stopped = True
                    break

                _log(f"--- задача {idx}/{total}: {task['project_name'] or '(без названия)'} "
                     f"[{task['language']}] {task['audio_filename']} ---")
                self._set_task_status(task["id"], status="running")
                self._set_progress(idx, total, "Готовится задача…", percent=round((idx - 1) / total * 100))

                try:
                    if draft_root is None or not osdetect.is_valid_draft_root(draft_root):
                        raise RuntimeError(
                            "Папка проектов CapCut не найдена. Укажи её вручную в настройках.")

                    def on_progress(msg, _idx=idx, _task=task):
                        _log(msg)
                        self._set_task_status(_task["id"], step=msg)
                        self._set_progress(_idx, total, msg)

                    on_progress("Распознаётся язык и выравниваются слова…")
                    result = self._align.request({
                        "cmd": "align",
                        "audio": task["audio_path"],
                        "text": task["text"],
                        "language": task["language"],
                        "model_size": cfg["model_size"],
                    }, on_progress=on_progress)
                    _log(f"выравнивание готово: {len(result['lines'])} строк субтитров, язык={result['language']}")

                    if self._stop_event.is_set():
                        stopped = True
                        break

                    on_progress("Собирается проект в CapCut…")
                    info = capcut_inject.create_project(
                        draft_root=draft_root,
                        project_name=task["project_name"], audio_path=task["audio_path"],
                        caption_lines=result["lines"],
                    )
                    _log(f"готово → проект «{info['name']}» ({info['folder']})")
                    self._set_task_status(task["id"], status="done", step=f"Готово → «{info['name']}»")

                except align_client.Cancelled:
                    stopped = True
                    _log("остановлено пользователем")
                    self._set_task_status(task["id"], status="cancelled", step="Остановлено")
                    break
                except Exception as e:
                    _log(f"ОШИБКА: {e}")
                    _log(traceback.format_exc())
                    self._set_task_status(task["id"], status="error", step="Ошибка", error=str(e))
                    with self._lock:
                        self._last_error = {"summary": str(e), "task_id": task["id"]}
                    break  # одна ошибка — стоп всей очереди, не молотим дальше вслепую

            if stopped:
                with self._lock:
                    for t in self._tasks:
                        if t["status"] in ("queued", "running"):
                            t["status"] = "cancelled"
                            t["step"] = "Остановлено"
                self._set_progress(0, total, "Остановлено пользователем", percent=0)
            elif not self._last_error:
                self._set_progress(total, total, "Готово", percent=100)

        finally:
            cfg_now = settings_mod.load()
            if cfg_now.get("auto_reopen_capcut", True):
                _log("переоткрывается CapCut…")
                capcut_app.reopen()
            _log("=== очередь завершена ===")
            with self._lock:
                self._running = False
            self._stop_event.clear()


worker = Worker()
