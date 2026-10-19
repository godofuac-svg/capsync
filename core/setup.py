"""
setup.py — экран первого запуска: проверяет и доустанавливает тяжёлые
зависимости (faster-whisper/stable-ts/ffmpeg) и прогревает скачивание
выбранной модели распознавания. launch.command ставит только лёгкий
bootstrap (fastapi/uvicorn/pywebview) — иначе окно и так открывалось бы
по 10+ минут при первом клике по .command-файлу на новой машине.
"""
import importlib
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from . import settings as settings_mod

_ROOT = Path(__file__).parent.parent


def _log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] [setup] {msg}", flush=True)

STEPS = [
    {"key": "ffmpeg", "label": "Проверка ffmpeg (чтение длительности аудио)"},
    {"key": "packages", "label": "Установка пакетов распознавания речи"},
    {"key": "model", "label": "Загрузка модели распознавания"},
]

_state_lock = threading.Lock()
_state = {
    "overall": "pending",  # pending | running | done | error
    "steps": {s["key"]: {"status": "pending", "detail": ""} for s in STEPS},
    "error": None,
}
_started = False


def status() -> dict:
    with _state_lock:
        return {
            "overall": _state["overall"],
            "error": _state["error"],
            "steps": [
                {"key": s["key"], "label": s["label"], **_state["steps"][s["key"]]}
                for s in STEPS
            ],
        }


def _set(key, status_, detail=""):
    with _state_lock:
        _state["steps"][key] = {"status": status_, "detail": detail}


def is_ready() -> bool:
    """Быстрая проверка без пересборки окружения — true, если всё уже на месте."""
    try:
        importlib.import_module("faster_whisper")
        importlib.import_module("stable_whisper")
    except ImportError:
        return False
    return _ffmpeg_path() is not None


_BIN_DIR = _ROOT / "work" / "bin"

# персистентная отметка "эта модель уже прогрета" — без неё run_setup() грузил бы модель
# заново КАЖДЫЙ запуск приложения (а не только когда реально нужно), и huggingface_hub
# на каждую загрузку ходит в сеть сверить версию файла, даже если он уже лежит локально.
_WARM_MARKERS_DIR = _ROOT / "work"


def _warm_marker(model_size: str) -> Path:
    return _WARM_MARKERS_DIR / f".model_ready_{model_size}"


def _ffmpeg_path() -> str | None:
    """stable-ts вызывает бинарь по жёсткому имени "ffmpeg" из PATH (свой путь передать
    нельзя — см. stable_whisper/audio.py load_audio) — поэтому если системного ffmpeg нет,
    не просто возвращаем путь к portable-бинарю, а кладём на него симлинк/копию с именем
    "ffmpeg"/"ffmpeg.exe" в work/bin и добавляем work/bin в PATH текущего процесса. Тогда
    "ffmpeg" из PATH резолвится для абсолютно любого кода ниже, включая align-сабпроцесс
    (он наследует os.environ при spawn)."""
    import os
    import shutil
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")

    try:
        import imageio_ffmpeg
    except ImportError:
        return None

    real_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    _BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = _BIN_DIR / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if not target.exists():
        try:
            target.symlink_to(real_exe)
        except OSError:
            import shutil as _sh
            _sh.copy2(real_exe, target)
            target.chmod(0o755)

    bin_dir_str = str(_BIN_DIR)
    if bin_dir_str not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = bin_dir_str + os.pathsep + os.environ.get("PATH", "")

    return shutil.which("ffmpeg")


def run_setup():
    """Идемпотентно — безопасно звать повторно, уже готовые шаги просто быстро проверяются заново."""
    global _started
    with _state_lock:
        if _started and _state["overall"] == "running":
            return
        _started = True
        _state["overall"] = "running"
        _state["error"] = None

    _log("=== экран первого запуска ===")
    try:
        _log("проверяется ffmpeg…")
        _set("ffmpeg", "running")
        if _ffmpeg_path() is None:
            _log("ffmpeg не найден — ставится portable-сборка (imageio-ffmpeg)…")
            _set("ffmpeg", "running", "Устанавливается portable-сборка ffmpeg…")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "imageio-ffmpeg"], check=True)
        if _ffmpeg_path() is None:
            raise RuntimeError("Не удалось получить рабочий ffmpeg")
        _log("ffmpeg ок")
        _set("ffmpeg", "done")

        _log("проверяются пакеты распознавания речи…")
        _set("packages", "running", "Проверяются пакеты распознавания речи…")
        import_errors = {}
        for mod in ("faster_whisper", "stable_whisper"):
            try:
                importlib.import_module(mod)
            except Exception as e:  # не только ImportError — DLL load failed это OSError
                import_errors[mod] = e

        if import_errors:
            # На Windows-сборке (embeddable Python) pip вообще не идёт в комплекте —
            # там всё уже вшито на этапе сборки пакета, и если импорт всё равно не
            # проходит, это НЕ лечится pip install (его там физически нет), а значит
            # и пытаться не нужно — это только прятало бы настоящую причину (например,
            # "DLL load failed" из-за отсутствующего Visual C++ Redistributable) за
            # бессмысленным "No module named pip".
            has_pip = importlib.util.find_spec("pip") is not None
            if has_pip:
                pip_names = {"faster_whisper": "faster-whisper", "stable_whisper": "stable-ts"}
                need = [pip_names[m] for m in import_errors]
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", *need], check=True)
                importlib.invalidate_caches()
                for mod in list(import_errors):
                    try:
                        importlib.import_module(mod)
                        del import_errors[mod]
                    except Exception as e:
                        import_errors[mod] = e

        if import_errors:
            details = "; ".join(f"{m}: {e}" for m, e in import_errors.items())
            raise RuntimeError(
                f"Не импортируются модули распознавания речи ({details}). "
                f"Похоже, не хватает Visual C++ Redistributable (x64) — поставь "
                f"https://aka.ms/vs/17/release/vc_redist.x64.exe и перезапусти.")
        _log("пакеты ок")
        _set("packages", "done")

        cfg = settings_mod.load()
        model_size = cfg["model_size"]
        marker = _warm_marker(model_size)
        if marker.is_file():
            _log(f"модель «{model_size}» уже прогрета ранее — пропускаю")
            _set("model", "done")  # уже прогревали эту модель раньше — не лезем в сеть повторно
        else:
            _log(f"грузится модель «{model_size}»…")
            _set("model", "running", f"Загружается модель «{model_size}» (в первый раз может занять несколько минут)…")
            from .align_client import AlignClient

            def on_progress(msg):
                _log(msg)
                _set("model", "running", msg)

            client = AlignClient(sys.executable)
            client.request({"cmd": "_warm", "model_size": model_size}, on_progress=on_progress)
            client.stop()
            _WARM_MARKERS_DIR.mkdir(parents=True, exist_ok=True)
            marker.touch()
            _log("модель загружена")
            _set("model", "done")

        _log("=== готово ===")
        with _state_lock:
            _state["overall"] = "done"
    except Exception as e:
        _log(f"ОШИБКА: {e}")
        _log(traceback.format_exc())
        with _state_lock:
            _state["overall"] = "error"
            _state["error"] = str(e)
        # шаг, на котором остановились, уже помечен running — помечаем его ошибкой
        with _state_lock:
            for s in STEPS:
                if _state["steps"][s["key"]]["status"] == "running":
                    _state["steps"][s["key"]] = {"status": "error", "detail": str(e)}
    finally:
        with _state_lock:
            _started = False
