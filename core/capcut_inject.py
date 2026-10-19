"""
capcut_inject.py — создаёт НОВЫЙ проект CapCut, клонируя проект-шаблон
(выбранный один раз в настройках) и подставляя туда:
  - озвучку задачи (материал audio);
  - субтитры по словам — материалы type:"subtitle" с полем "words"
    (локальные мс-тайминги относительно начала строки) — именно так
    хранит тайминги родной Auto Captions в CapCut, это разобрано руками
    на реальном черновике (project 1018, см. историю чата).

Почему клонируем существующий проект, а не собираем draft_info.json с нуля:
хэндролленый скелет рискует не содержать какое-то поле, которое текущая
версия CapCut считает обязательным, и тогда проект просто не откроется.
Клонирование реального, созданного самим CapCut проекта гарантированно
рабочее — это уже проверено на практике.
"""
import json
import os
import random
import shutil
import subprocess
import time
import uuid
from pathlib import Path

ADJ = ["NEON", "ACID", "GHOST", "FERAL", "RAPID", "VOLT", "CRIMSON", "ROGUE", "STATIC", "BLAZE"]
NOUN = ["FOX", "WOLF", "HAWK", "VIPER", "PULSE", "ECHO", "SHARD", "RIFT", "SPARK", "CIPHER"]

# Шаблон зашит внутри тула (assets/template_draft) — универсальный пустой CapCut-проект
# (audio+text трек, без видео, без личного контента), один раз собранный из реального
# проекта, сгенерированного самим CapCut, чтобы гарантированно открывался. Из-за этого
# не нужно просить каждого из 10 человек в команде вручную создавать и выбирать свой
# проект-шаблон в настройках — работает из коробки на любой машине.
TEMPLATE_PATH = Path(__file__).parent.parent / "assets" / "template_draft"


def random_project_name() -> str:
    return f"{random.choice(ADJ)}_{random.choice(NOUN)}_{uuid.uuid4().hex[:4].upper()}"


def _atomic_write_json(path: Path, data: dict):
    tmp = path.with_suffix(path.suffix + f".tmp{uuid.uuid4().hex[:6]}")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _snap_frames(us: float, fps: float) -> int:
    frame_us = 1_000_000 / fps
    return int(round(round(us / frame_us) * frame_us))


def _ffprobe_duration_seconds(path: str) -> float:
    import shutil
    if shutil.which("ffprobe"):
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stderr=subprocess.STDOUT,
        )
        return float(out.decode().strip())
    # нет ffprobe (только ffmpeg, возможно наш portable-шим из setup.py — см. _ffmpeg_path) —
    # длительность парсим из "ffmpeg -i" stderr
    import re
    out = subprocess.run(["ffmpeg", "-i", path], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out.stderr.decode(errors="ignore"))
    if not m:
        raise RuntimeError(f"Не удалось определить длительность аудио: {path}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def build_caption_material(template_material: dict, line: list[dict], fps: float) -> tuple[dict, float, float]:
    """line: [{"word": str, "start": sec, "end": sec}, ...] (абсолютное время в рамках аудио).
    Возвращает (материал, абс.старт сек, абс.конец сек)."""
    import copy
    mat = copy.deepcopy(template_material)
    line_start_s = line[0]["start"]
    line_end_s = line[-1]["end"]

    mat["id"] = str(uuid.uuid4()).upper()
    mat["recognize_task_id"] = ""
    mat["recognize_model"] = ""
    mat["punc_model"] = ""
    mat["type"] = "subtitle"

    full_text = " ".join(w["word"] for w in line)
    mat["recognize_text"] = full_text

    content_obj = {
        "styles": [{
            "fill": {"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": [1.0, 1.0, 1.0]}}},
            "font": {"id": "", "path": ""},
            "range": [0, len(full_text)],
            "size": 10.0,
        }],
        "text": full_text,
    }
    content_str = json.dumps(content_obj, ensure_ascii=False)
    mat["content"] = content_str
    mat["base_content"] = content_str

    words_text, words_start, words_end = [], [], []
    for i, w in enumerate(line):
        local_start = round((w["start"] - line_start_s) * 1000)
        local_end = round((w["end"] - line_start_s) * 1000)
        words_text.append(w["word"])
        words_start.append(local_start)
        words_end.append(local_end)
        if i < len(line) - 1:
            words_text.append(" ")
            words_start.append(local_end)
            words_end.append(local_end)

    mat["words"] = {"start_time": words_start, "end_time": words_end, "text": words_text}
    mat["current_words"] = {"start_time": [], "end_time": [], "text": []}
    mat["caption_template_info"] = {
        "resource_id": "", "third_resource_id": "", "resource_name": "",
        "category_id": "", "category_name": "", "effect_id": "", "request_id": "",
        "path": "", "is_new": False, "source_platform": 0,
    }
    mat["combo_info"] = {"text_templates": []}
    return mat, line_start_s, line_end_s


def _log(msg: str):
    import time
    print(f"[{time.strftime('%H:%M:%S')}]   {msg}", flush=True)


def create_project(draft_root: Path, project_name: str | None,
                    audio_path: str, caption_lines: list[list[dict]]) -> dict:
    if not (TEMPLATE_PATH / "draft_info.json").is_file():
        raise FileNotFoundError(f"Встроенный шаблон не найден: {TEMPLATE_PATH} — переустанови CapSync.")

    new_folder = f"capsync_{uuid.uuid4().hex[:12]}"
    dest_path = draft_root / new_folder
    _log(f"клонируется шаблон -> {new_folder}")
    shutil.copytree(TEMPLATE_PATH, dest_path)

    draft_file = dest_path / "draft_info.json"
    d = json.loads(draft_file.read_text(encoding="utf-8"))
    fps = float(d.get("fps") or 30.0)

    text_track = next((t for t in d["tracks"] if t["type"] == "text"), None)
    audio_track = next((t for t in d["tracks"] if t["type"] == "audio"), None)
    if text_track is None or audio_track is None:
        raise RuntimeError("В проекте-шаблоне нет audio- и text-трека — выбери другой шаблон "
                            "(создай в CapCut пустой проект и добавь в него любую аудиодорожку).")

    # ВАЖНО: донор схемы должен быть ПОЛНЫМ реальным объектом из шаблона (у текстового
    # материала CapCut ~127 полей — тени/обводка/typesetting/пресеты и т.д.), а не наш
    # урезанный словарь на десяток полей. Ровно это и роняло CapCut при открытии —
    # шаблон был зачищен вместе с формой, а не только с личным контентом. Если шаблона
    # нет совсем — это испорченная установка, а не штатный случай, который стоит тихо
    # подменять суррогатом.
    if not d["materials"]["texts"] or not text_track["segments"]:
        raise RuntimeError(f"Встроенный шаблон повреждён (нет донора текстового материала/сегмента): {TEMPLATE_PATH}")
    template_material = d["materials"]["texts"][0]
    template_segment = text_track["segments"][0]

    import copy
    d["materials"]["texts"] = []
    text_track["segments"] = []

    for line in caption_lines:
        mat, start_s, end_s = build_caption_material(template_material, line, fps)
        d["materials"]["texts"].append(mat)
        seg = copy.deepcopy(template_segment)
        seg["id"] = str(uuid.uuid4()).upper()
        seg["material_id"] = mat["id"]
        seg["extra_material_refs"] = []
        seg["caption_info"] = None
        start_us = _snap_frames(start_s * 1_000_000, fps)
        end_us = _snap_frames(end_s * 1_000_000, fps)
        seg["target_timerange"] = {"start": start_us, "duration": max(end_us - start_us, 1)}
        seg["source_timerange"] = None
        text_track["segments"].append(seg)

    _log(f"собрано {len(caption_lines)} субтитров-сегментов")

    dur_s = _ffprobe_duration_seconds(audio_path)
    dur_us = _snap_frames(dur_s * 1_000_000, fps)
    _log(f"длительность аудио: {dur_s:.2f}с")

    if not d["materials"]["audios"] or not audio_track["segments"]:
        raise RuntimeError(f"Встроенный шаблон повреждён (нет донора аудио-материала/сегмента): {TEMPLATE_PATH}")

    audio_mat = d["materials"]["audios"][0]  # полный реальный объект (66 полей) — меняем только контент
    audio_mat["path"] = audio_path
    audio_mat["name"] = os.path.basename(audio_path)
    audio_mat["duration"] = dur_us

    audio_seg = audio_track["segments"][0]
    audio_seg["source_timerange"] = {"start": 0, "duration": dur_us}
    audio_seg["target_timerange"] = {"start": 0, "duration": dur_us}
    audio_seg["material_id"] = audio_mat["id"]

    d["duration"] = max(d.get("duration") or 0, dur_us)
    old_id = d["id"]
    new_id = str(uuid.uuid4()).upper()
    d["id"] = new_id

    _atomic_write_json(draft_file, d)
    json.loads(draft_file.read_text(encoding="utf-8"))  # sanity reload
    _log("draft_info.json записан")

    _sync_timeline_id(dest_path, old_id, new_id, d)
    _log("ID таймлайна синхронизирован (draft_biz_config/timeline_layout/Timelines)")

    display_name = project_name or random_project_name()
    _register_in_root_index(draft_root, dest_path, display_name, dur_us)
    _log(f"зарегистрировано в CapCut как «{display_name}»")

    return {"folder": new_folder, "path": str(dest_path), "name": display_name}


def _sync_timeline_id(dest_path: Path, old_id: str, new_id: str, final_draft: dict):
    """draft_info.json["id"] на самом деле ID ТАЙМЛАЙНА, а не просто проекта — он
    буквально зашит ещё в 4 местах, и CapCut падает, если они расходятся (похоже,
    именно это и роняло CapCut при добавлении видео руками — проверено на реальном
    проекте 1018: draft_biz_config.json, timeline_layout.json, template-2.tmp и
    зеркальная копия в Timelines/<id>/ — все пять мест должны совпадать."""
    # 1) draft_biz_config.json — ключ timeline_settings
    biz_path = dest_path / "draft_biz_config.json"
    if biz_path.is_file():
        biz = json.loads(biz_path.read_text(encoding="utf-8"))
        settings = biz.get("timeline_settings", {})
        if old_id in settings:
            settings[new_id] = settings.pop(old_id)
            biz["timeline_settings"] = settings
            _atomic_write_json(biz_path, biz)

    # 2) timeline_layout.json — список открытых таймлайнов в UI
    layout_path = dest_path / "timeline_layout.json"
    if layout_path.is_file():
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        for item in layout.get("dockItems", []):
            item["timelineIds"] = [new_id if tid == old_id else tid for tid in item.get("timelineIds", [])]
        _atomic_write_json(layout_path, layout)

    # 3) template-2.tmp — полный снапшот draft_info.json (тот же формат) — просто
    # зеркалим финальный контент, чтобы не было рассинхрона со старым содержимым
    tmp_path = dest_path / "template-2.tmp"
    if tmp_path.is_file():
        _atomic_write_json(tmp_path, final_draft)

    # 4) Timelines/<old_id>/ -> Timelines/<new_id>/ — папка-кэш таймлайна, внутри
    # зеркальная копия draft_info.json (байт-в-байт с корневым, проверено на 1018)
    timelines_dir = dest_path / "Timelines"
    old_tl_dir = timelines_dir / old_id
    new_tl_dir = timelines_dir / new_id
    if old_tl_dir.is_dir():
        old_tl_dir.rename(new_tl_dir)

        for fname in ("draft_info.json", "draft_info.json.bak", "template-2.tmp"):
            fpath = new_tl_dir / fname
            if fpath.is_file():
                _atomic_write_json(fpath, final_draft)

        # patch-файл (mini_draft.json) — производные данные с ВСТРОЕННЫМИ id сегментов
        # старого контента; корректно пересобрать его сами мы не можем, а рассинхрон
        # с реальным draft_info.json — ровно то, что подозреваем в краше при добавлении
        # клипа. Безопаснее удалить и дать CapCut пересобрать с нуля, чем оставить stale.
        patch_dir = new_tl_dir / "attachment" / "patch"
        if patch_dir.is_dir():
            shutil.rmtree(patch_dir)

    # 5) project.json внутри Timelines/ — реестр таймлайнов проекта
    project_json_path = timelines_dir / "project.json"
    if project_json_path.is_file():
        proj = json.loads(project_json_path.read_text(encoding="utf-8"))
        if proj.get("main_timeline_id") == old_id:
            proj["main_timeline_id"] = new_id
        for tl in proj.get("timelines", []):
            if tl.get("id") == old_id:
                tl["id"] = new_id
        _atomic_write_json(project_json_path, proj)
        bak_path = timelines_dir / "project.json.bak"
        if bak_path.is_file():
            shutil.copy2(project_json_path, bak_path)


def _register_in_root_index(draft_root: Path, dest_path: Path, display_name: str, dur_us: int):
    root_meta_path = draft_root / "root_meta_info.json"
    root = json.loads(root_meta_path.read_text(encoding="utf-8")) if root_meta_path.is_file() else {
        "all_draft_store": [], "draft_ids": 0, "root_path": str(draft_root)}

    root["all_draft_store"] = [e for e in root["all_draft_store"] if e.get("draft_fold_path") != str(dest_path)]

    now_us = int(time.time() * 1_000_000)
    entry = {
        "cloud_draft_cover": False, "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False, "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": str(dest_path / "draft_cover.jpg"),
        "draft_fold_path": str(dest_path),
        "draft_id": str(uuid.uuid4()).upper(),
        "draft_is_ai_shorts": False, "draft_is_cloud_temp_draft": False,
        "draft_is_infinite_canvas_draft": False, "draft_is_invisible": False,
        "draft_is_pippit_draft": False, "draft_is_web_article_video": False,
        "draft_json_file": str(dest_path / "draft_info.json"),
        "draft_name": display_name,
        "draft_new_version": "", "draft_root_path": str(draft_root),
        "draft_timeline_materials_size": 0, "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "pippit_avatar_url": "", "pippit_extra_info": "", "pippit_id": "", "pippit_user_name": "",
        "streaming_edit_draft_ready": True,
        "tm_draft_cloud_completed": "", "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0, "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1, "tm_draft_cloud_user_id": -1,
        "tm_draft_create": now_us, "tm_draft_modified": now_us,
        "tm_draft_removed": 0, "tm_duration": dur_us,
    }
    root["all_draft_store"].append(entry)
    root["draft_ids"] = root.get("draft_ids", 0) + 1
    _atomic_write_json(root_meta_path, root)
    json.loads(root_meta_path.read_text(encoding="utf-8"))  # sanity reload
