"""
app.py — CapSync backend (FastAPI). Поднимается в фоновом потоке из run.py,
окно даёт pywebview. Вся обработка очереди — в core/worker.py (отдельный
поток + отдельный процесс для align, чтобы Стоп рвал работу мгновенно).
"""
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core import langs, osdetect, setup as setup_mod, textlang
from core import settings as settings_mod
from core.worker import worker

_ROOT = Path(__file__).parent
_STATIC = _ROOT / "static"
_WORK = _ROOT / "work"
_WORK.mkdir(exist_ok=True)
_LOGS_DIR = _WORK / "logs"

app = FastAPI()
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")


# ---------- setup (первый запуск / проверка зависимостей) ----------

@app.get("/api/setup/status")
def setup_status():
    return setup_mod.status()


@app.post("/api/setup/run")
def setup_run():
    import threading
    threading.Thread(target=setup_mod.run_setup, daemon=True).start()
    return {"ok": True}


@app.get("/api/setup/ready")
def setup_ready():
    return {"ready": setup_mod.is_ready()}


# ---------- справочники ----------

@app.get("/api/langs")
def api_langs():
    return langs.options_for_frontend()


@app.post("/api/detect_language")
def detect_language(payload: dict):
    """Дёргается фронтендом по тексту задачи (с дебаунсом), ДО Старта — текст это
    точный скрипт озвучки, определять по нему быстрее и надёжнее, чем по аудио."""
    text = (payload.get("text") or "").strip()
    if len(text) < 3:
        return {"language": None, "label": None}
    return textlang.detect(text)


# ---------- настройки ----------

@app.get("/api/settings")
def get_settings():
    return settings_mod.load()


@app.post("/api/settings")
def post_settings(patch: dict):
    return settings_mod.save(patch)


@app.post("/api/capcut/folder")
def set_capcut_folder(payload: dict):
    path = Path(payload.get("path", ""))
    if not osdetect.is_valid_draft_root(path):
        return JSONResponse({"ok": False, "error": "В этой папке не найден root_meta_info.json — это не папка com.lveditor.draft"}, status_code=400)
    settings_mod.save({"capcut_folder": str(path)})
    return {"ok": True}


# ---------- очередь задач ----------

@app.get("/api/state")
def api_state():
    return worker.state()


@app.post("/api/tasks")
async def add_task(
    text: str = Form(...),
    project_name: str = Form(""),
    language: str = Form("auto"),
    audio: UploadFile = None,
):
    task_id = uuid.uuid4().hex[:10]
    task_dir = _WORK / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    audio_path = task_dir / audio.filename
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    real_id = worker.add_task(
        text=text.strip(),
        audio_path=str(audio_path),
        project_name=project_name.strip() or None,
        language=language,
    )
    return {"id": real_id}


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    ok = worker.remove_task(task_id)
    return {"ok": ok}


@app.delete("/api/tasks")
def clear_tasks():
    worker.clear_finished()
    return {"ok": True}


@app.post("/api/start")
def start():
    worker.start()
    return {"ok": True}


@app.post("/api/stop")
def stop():
    worker.stop()
    return {"ok": True}


@app.get("/api/log")
def get_log(path: str):
    p = Path(path).resolve()
    if _LOGS_DIR.resolve() not in p.parents or not p.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(p, filename=p.name, media_type="text/plain")
