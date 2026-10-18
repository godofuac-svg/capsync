#!/bin/bash
# Двойной клик в Finder → CapSync.
# Первый запуск сам ставит venv + лёгкие зависимости (окно должно открыться за секунды).
# Тяжёлые зависимости (faster-whisper/stable-ts/ffmpeg) и модель распознавания доставит
# сам CapSync на экране первого запуска — see core/setup.py. Если бы их ставил этот
# .command, пользователь ждал бы 10+ минут в терминале прежде чем увидеть хоть что-то.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

die() { echo; echo "✗ $1"; echo; echo "(окно можно закрыть)"; read -r _; exit 1; }

echo "==============================================="
echo "  CapSync — FMB Team"
echo "==============================================="

# 1) python: нужна версия с готовыми (не исходниковыми) wheel-ами под ctranslate2/av —
# самые новые Python (3.14/3.15 на свежих машинах) этого ещё не имеют и ломаются на
# сборке из исходников. Перебираем версии, которые точно работают, в порядке предпочтения.
PYTHON_BIN=""
for v in python3.11 python3.12 python3.10; do
  if command -v "$v" >/dev/null 2>&1; then
    PYTHON_BIN="$v"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "▸ не найден подходящий Python — ставлю python@3.11 через Homebrew (1-2 мин)…"
    brew install python@3.11 || die "не удалось поставить python@3.11 через brew"
    PYTHON_BIN="$(brew --prefix python@3.11)/bin/python3.11"
  else
    die "нужен Python 3.10-3.12 и его нет. Поставь Homebrew (brew.sh), потом запусти снова."
  fi
fi

echo "▸ использую $PYTHON_BIN ($("$PYTHON_BIN" --version))"

# 2) venv (создаём только при первом запуске — это дорогая часть)
if [ ! -x ".venv/bin/python" ]; then
  echo "▸ первый запуск: создаю окружение…"
  rm -rf .venv
  "$PYTHON_BIN" -m venv .venv || die "не удалось создать venv"
  ./.venv/bin/pip install -q --upgrade pip
fi

# 2б) лёгкие зависимости — синхронизируем КАЖДЫЙ запуск, не только первый. venv может
# быть старым (создан до того, как в requirements-bootstrap.txt добавили новый пакет),
# а pip install на уже удовлетворённых зависимостях — это доля секунды, не полная
# переустановка. Без этого шага обновление тула молча ломалось бы с ModuleNotFoundError.
./.venv/bin/pip install -q -r requirements-bootstrap.txt || die "pip install упал (см. вывод выше)"

# 3) поехали — тяжёлые зависимости и модель CapSync доставит сам, на экране первого запуска.
# exit 7 = run.py сам скачал обновление кода (core/selfupdate.py) в app_new/ — подменяем
# лёгкие файлы поверх (python/-венв и прочее тяжёлое в app_new/ нет, его не трогаем) и
# перезапускаемся тем же циклом, без повторной выдачи .command всей команде.
echo "▸ запускаю CapSync…"
while true; do
  ./.venv/bin/python run.py
  rc=$?
  if [ "$rc" -eq 7 ] && [ -d "app_new" ]; then
    echo "▸ применяю обновление…"
    cp -R app_new/. .
    rm -rf app_new
    continue
  fi
  exit "$rc"
done
