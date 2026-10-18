"""
osdetect.py — определяет ОС и ищет папку CapCut Projects (com.lveditor.draft).

Путь к черновикам CapCut не задокументирован официально и отличается по
установкам, поэтому тут только лучшие предположения по умолчанию + ручной
override хранится в settings.json (см. core/settings.py).
"""
import os
import platform
from pathlib import Path

OS_NAME = platform.system()  # "Darwin" | "Windows" | "Linux"


def os_label() -> str:
    return {"Darwin": "mac", "Windows": "windows", "Linux": "linux"}.get(OS_NAME, "unknown")


def _candidates() -> list[Path]:
    home = Path.home()
    if OS_NAME == "Darwin":
        return [home / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"]
    if OS_NAME == "Windows":
        local = os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
        return [
            Path(local) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
            Path(local) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft.unicode",
        ]
    return []


def is_valid_draft_root(p: Path) -> bool:
    """Папка валидна, если в ней лежит root_meta_info.json — индекс, который сам CapCut
    использует для списка проектов (см. разбор в черновике 1018)."""
    return (p / "root_meta_info.json").is_file()


def autodetect() -> Path | None:
    for c in _candidates():
        if is_valid_draft_root(c):
            return c
    return None


def instructions_text() -> str:
    if OS_NAME == "Darwin":
        return (
            "Папка черновиков не найдена автоматически.\n\n"
            "1. Открой CapCut → в любом проекте нажми правой кнопкой на обложку проекта "
            "в списке проектов → «Показать в Finder» (Show in Finder).\n"
            "2. В Finder подними на один уровень выше, до папки с именем вроде "
            "«com.lveditor.draft» — это и есть нужная папка.\n"
            "3. Скопируй её путь (⌥ (Option) + правый клик на папке → «Копировать как путь») "
            "и вставь в поле ниже."
        )
    if OS_NAME == "Windows":
        return (
            "Папка черновиков не найдена автоматически.\n\n"
            "1. Открой CapCut → в любом проекте нажми правой кнопкой на обложку проекта "
            "в списке проектов → «Show in Explorer».\n"
            "2. В Explorer поднимись на уровень выше, до папки «com.lveditor.draft».\n"
            "3. Скопируй путь из адресной строки Explorer и вставь в поле ниже."
        )
    return "ОС не поддерживается автоопределением — укажи путь к com.lveditor.draft вручную."


def list_projects(draft_root: Path) -> list[dict]:
    """Проекты, уже существующие в CapCut (для выбора проекта-шаблона в настройках)."""
    out = []
    if not draft_root.is_dir():
        return out
    for child in sorted(draft_root.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
        if not child.is_dir() or child.name.startswith("."):
            continue
        info = child / "draft_info.json"
        meta = child / "draft_meta_info.json"
        if not info.is_file():
            continue
        name = child.name
        try:
            import json
            if meta.is_file():
                m = json.loads(meta.read_text(encoding="utf-8"))
                name = m.get("draft_name") or name
        except Exception:
            pass
        out.append({"folder": child.name, "name": name, "path": str(child)})
    return out
