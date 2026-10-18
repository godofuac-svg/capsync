"""
textlang.py — определение языка ПО ТЕКСТУ задачи, а не по аудио. Текст — это
именно тот скрипт, что отдавался в TTS, то есть точный источник истины;
определять язык по сгенерированной озвучке (акустикой) и медленнее (нужна
модель), и менее надёжно (акцент/качество голоса TTS может сбить акустический
детектор), и не нужно ждать прикрепления файла — текст уже есть.
"""
import langid

from .langs import LANGUAGES


def detect(text: str) -> dict:
    code, _score = langid.classify(text)
    name = LANGUAGES.get(code, code)
    return {"language": code, "label": f"{name} ({code})"}
