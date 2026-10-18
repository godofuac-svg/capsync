"""langs.py — список языков, которые понимает Whisper (используется и для
forced alignment, и для автоопределения). Статический список — не тащим сюда
тяжёлые ML-импорты только чтобы отрисовать dropdown."""

LANGUAGES = {
    "en": "English", "zh": "Chinese", "de": "German", "es": "Spanish", "ru": "Russian",
    "ko": "Korean", "fr": "French", "ja": "Japanese", "pt": "Portuguese", "tr": "Turkish",
    "pl": "Polish", "ca": "Catalan", "nl": "Dutch", "ar": "Arabic", "sv": "Swedish",
    "it": "Italian", "id": "Indonesian", "hi": "Hindi", "fi": "Finnish", "vi": "Vietnamese",
    "he": "Hebrew", "uk": "Ukrainian", "el": "Greek", "ms": "Malay", "cs": "Czech",
    "ro": "Romanian", "da": "Danish", "hu": "Hungarian", "ta": "Tamil", "no": "Norwegian",
    "th": "Thai", "ur": "Urdu", "hr": "Croatian", "bg": "Bulgarian", "lt": "Lithuanian",
    "la": "Latin", "mi": "Maori", "ml": "Malayalam", "cy": "Welsh", "sk": "Slovak",
    "te": "Telugu", "fa": "Persian", "lv": "Latvian", "bn": "Bengali", "sr": "Serbian",
    "az": "Azerbaijani", "sl": "Slovenian", "kn": "Kannada", "et": "Estonian",
    "mk": "Macedonian", "br": "Breton", "eu": "Basque", "is": "Icelandic", "hy": "Armenian",
    "ne": "Nepali", "mn": "Mongolian", "bs": "Bosnian", "kk": "Kazakh", "sq": "Albanian",
    "sw": "Swahili", "gl": "Galician", "mr": "Marathi", "pa": "Punjabi", "si": "Sinhala",
    "km": "Khmer", "sn": "Shona", "yo": "Yoruba", "so": "Somali", "af": "Afrikaans",
    "oc": "Occitan", "ka": "Georgian", "be": "Belarusian", "tg": "Tajik", "sd": "Sindhi",
    "gu": "Gujarati", "am": "Amharic", "yi": "Yiddish", "lo": "Lao", "uz": "Uzbek",
    "fo": "Faroese", "ht": "Haitian Creole", "ps": "Pashto", "tk": "Turkmen",
    "nn": "Nynorsk", "mt": "Maltese", "sa": "Sanskrit", "lb": "Luxembourgish",
    "my": "Myanmar", "bo": "Tibetan", "tl": "Tagalog", "mg": "Malagasy", "as": "Assamese",
    "tt": "Tatar", "haw": "Hawaiian", "ln": "Lingala", "ha": "Hausa", "ba": "Bashkir",
    "jw": "Javanese", "su": "Sundanese", "yue": "Cantonese",
}

AUTODETECT = "auto"

# язык → страна для флага (flag-icons, ISO 3166-1). Это условность — у языка может не
# быть "своей" страны (lingua franca, региональные языки) — тогда берётся самая
# узнаваемая ассоциация. Чисто декоративно, для дропдауна.
FLAG = {
    "en": "gb", "zh": "cn", "de": "de", "es": "es", "ru": "ru", "ko": "kr", "fr": "fr",
    "ja": "jp", "pt": "pt", "tr": "tr", "pl": "pl", "ca": "es", "nl": "nl", "ar": "sa",
    "sv": "se", "it": "it", "id": "id", "hi": "in", "fi": "fi", "vi": "vn", "he": "il",
    "uk": "ua", "el": "gr", "ms": "my", "cs": "cz", "ro": "ro", "da": "dk", "hu": "hu",
    "ta": "in", "no": "no", "th": "th", "ur": "pk", "hr": "hr", "bg": "bg", "lt": "lt",
    "la": "va", "mi": "nz", "ml": "in", "cy": "gb", "sk": "sk", "te": "in", "fa": "ir",
    "lv": "lv", "bn": "bd", "sr": "rs", "az": "az", "sl": "si", "kn": "in", "et": "ee",
    "mk": "mk", "br": "fr", "eu": "es", "is": "is", "hy": "am", "ne": "np", "mn": "mn",
    "bs": "ba", "kk": "kz", "sq": "al", "sw": "ke", "gl": "es", "mr": "in", "pa": "in",
    "si": "lk", "km": "kh", "sn": "zw", "yo": "ng", "so": "so", "af": "za", "oc": "fr",
    "ka": "ge", "be": "by", "tg": "tj", "sd": "pk", "gu": "in", "am": "et", "yi": "il",
    "lo": "la", "uz": "uz", "fo": "fo", "ht": "ht", "ps": "af", "tk": "tm", "nn": "no",
    "mt": "mt", "sa": "in", "lb": "lu", "my": "mm", "bo": "cn", "tl": "ph", "mg": "mg",
    "as": "in", "tt": "ru", "haw": "us", "ln": "cd", "ha": "ng", "ba": "ru", "jw": "id",
    "su": "id", "yue": "hk",
}


def options_for_frontend() -> list[dict]:
    opts = [{"value": AUTODETECT, "label": "Автоопределение", "flag": None}]
    for code, name in sorted(LANGUAGES.items(), key=lambda kv: kv[1]):
        opts.append({"value": code, "label": f"{name} ({code})", "flag": FLAG.get(code)})
    return opts
