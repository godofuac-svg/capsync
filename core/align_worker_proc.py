"""
align_worker_proc.py — отдельный ПРОЦЕСС (не поток) для forced alignment.

Почему отдельный процесс, а не поток: ctranslate2/faster-whisper инференс —
это один долгий C++-вызов, который питоновский GIL/threading.Event не
прервут на середине. А кнопка «Стоп» должна рвать работу «в ту же секунду» —
единственный надёжный способ это сделать — убить сам процесс (SIGKILL),
а не ждать, пока он кооперативно проверит флаг отмены.

Протокол: по одной JSON-строке на stdin, в ответ одна или больше JSON-строк
на stdout (сначала progress-сообщения, в конце result/error). Родитель читает
построчно и убивает процесс при Stop — тогда readline() в родителе просто
получает EOF, без зависаний.
"""
import json
import sys
import traceback

_model_cache = {}  # {model_size: loaded faster-whisper model} — живёт всю жизнь процесса


def _emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _progress(message):
    _emit({"type": "progress", "message": message})


def _get_model(model_size):
    import stable_whisper
    if model_size not in _model_cache:
        _progress(f"Загружается модель распознавания «{model_size}»…")
        _model_cache.clear()  # держим только одну модель в памяти одновременно
        # compute_type="int8": на CPU без этого ctranslate2 считает в float32 (предупреждение
        # "float16 не поддерживается, перевожу в float32" — это самый медленный путь).
        # На реальном прогоне (47с аудио, large-v3) int8 дал 6 секунд вместо ~210 — то же
        # качество, в ~35 раз быстрее. Это и есть ответ на "почему 40-секундная задача
        # идёт так долго" — раньше шла в float32, теперь не должна.
        _model_cache[model_size] = stable_whisper.load_faster_whisper(model_size, compute_type="int8")
    return _model_cache[model_size]


def _detect_language(req):
    import stable_whisper.audio as swa
    model = _get_model(req["model_size"])
    _progress("Определяется язык аудио…")
    audio = swa.load_audio(req["audio"])
    language, probability, _all = model.detect_language(audio)
    return {"language": language, "probability": round(float(probability), 3)}


def _align(req):
    import stable_whisper
    model = _get_model(req["model_size"])
    language = req["language"]
    if language == "auto":
        info = _detect_language(req)
        language = info["language"]
        _progress(f"Определён язык: {language} ({info['probability']*100:.0f}%)")

    _progress("Выравниваются слова по аудио (forced alignment)…")
    result = model.align(req["audio"], req["text"], language=language)

    _progress("Разбиваются строки субтитров…")
    result.regroup("da")

    lines = []
    for seg in result.segments:
        words = [{"word": w.word.strip(), "start": w.start, "end": w.end}
                 for w in seg.words if w.word.strip()]
        if words:
            lines.append(words)

    return {"language": language, "lines": lines}


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except Exception:
            continue
        try:
            if req["cmd"] == "detect_language":
                res = _detect_language(req)
            elif req["cmd"] == "align":
                res = _align(req)
            elif req["cmd"] == "ping":
                res = {"pong": True}
            elif req["cmd"] == "_warm":
                _get_model(req["model_size"])
                res = {"ok": True}
            else:
                raise ValueError(f"unknown cmd {req.get('cmd')}")
            _emit({"type": "result", "data": res})
        except Exception as e:
            _emit({"type": "error", "message": str(e), "traceback": traceback.format_exc()})


if __name__ == "__main__":
    main()
