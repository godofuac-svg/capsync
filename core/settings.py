"""settings.py — настройки, переживающие перезапуск (JSON-файл рядом с приложением)."""
import json
import threading
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_FILE = _ROOT / "settings.json"
_lock = threading.Lock()

DEFAULTS = {
    "capcut_folder": None,       # override пути к com.lveditor.draft; None = доверяем автодетекту
    "model_size": "large-v3",    # tiny / base / small / medium / large-v3 / large-v3-turbo
    "auto_reopen_capcut": True,  # закрыть CapCut перед прогоном мы делаем ВСЕГДА (гонка записи
                                  # в root_meta_info.json); этот тумблер — только про то, открывать
                                  # ли его обратно после того как вся очередь обработана
}

MODEL_CHOICES = [
    {"value": "tiny", "label": "tiny — самый быстрый, грубые тайминги"},
    {"value": "small", "label": "small — быстро, средняя точность"},
    {"value": "medium", "label": "medium — баланс скорости и точности"},
    {"value": "large-v3", "label": "large-v3 — максимальная точность (рекомендовано)"},
    {"value": "large-v3-turbo", "label": "large-v3-turbo — почти как large-v3, но быстрее"},
]


def load() -> dict:
    with _lock:
        if not _FILE.is_file():
            return dict(DEFAULTS)
        try:
            data = json.loads(_FILE.read_text(encoding="utf-8"))
        except Exception:
            return dict(DEFAULTS)
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in data.items() if k in DEFAULTS})
        return merged


def save(patch: dict) -> dict:
    with _lock:
        current = dict(DEFAULTS)
        if _FILE.is_file():
            try:
                current.update({k: v for k, v in json.loads(_FILE.read_text(encoding="utf-8")).items() if k in DEFAULTS})
            except Exception:
                pass
        current.update({k: v for k, v in patch.items() if k in DEFAULTS})
        _FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        return current
