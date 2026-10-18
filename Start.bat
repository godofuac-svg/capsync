@echo off
chcp 65001 >nul
title CapSync
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
rem ffmpeg.exe/ffprobe.exe лежат рядом с нами — кладём их в PATH, чтобы stable-ts
rem (который дёргает "ffmpeg" по жёсткому имени, без своего пути) их нашёл сразу,
rem без скачивания portable-сборки на экране первого запуска.
set PATH=%~dp0ffmpeg;%PATH%

rem torch/ctranslate2/onnxruntime — всё скомпилировано под Visual C++ Redistributable,
rem а на чистой Windows его может не быть -> "DLL load failed" при импорте пакетов
rem распознавания. Ставим один раз (маркер .vcredist_ok), тихо, один UAC-запрос.
if not exist "%~dp0.vcredist_ok" (
  echo Проверяю Visual C++ Redistributable...
  "%~dp0vc_redist.x64.exe" /install /quiet /norestart
  echo ok > "%~dp0.vcredist_ok"
)

:run
"%~dp0python\python.exe" -X utf8 run.py
rem exit 7 = run.py сам скачал обновление кода (core/selfupdate.py) в app_new\ —
rem подменяем лёгкие файлы поверх (python\ и ffmpeg\ там нет, тяжёлое не трогаем)
rem и перезапускаемся, без переотправки всего инсталлятора команде.
if errorlevel 8 goto done
if errorlevel 7 (
  if exist "%~dp0app_new" (
    robocopy "%~dp0app_new" "%~dp0" /E /NFL /NDL /NJH /NJS /NC /NS >nul
    rmdir /s /q "%~dp0app_new"
  )
  goto run
)
:done
if errorlevel 1 pause
