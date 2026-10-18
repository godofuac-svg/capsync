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
rem а на чистой Windows его может не быть -> "DLL load failed", которое Python из-за
rem особенностей инициализации torch иногда показывает как обманчивое "circular import"
rem вместо настоящей причины. Ставим один раз (маркер .vcredist_ok) — но ВАЖНО: этому
rem инсталлятору нужны права администратора, а сам Start.bat их не имеет, поэтому
rem повышаем права именно для этой команды через PowerShell (-Verb RunAs — это и
rem есть сам UAC-запрос) и ПРОВЕРЯЕМ код возврата, а не считаем успехом вслепую.
if not exist "%~dp0.vcredist_ok" (
  echo Проверяю Visual C++ Redistributable...
  powershell -NoProfile -Command ^
    "$p = Start-Process -FilePath '%~dp0vc_redist.x64.exe' -ArgumentList '/install','/quiet','/norestart' -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
  set VCRC=%ERRORLEVEL%
  rem 0 = ok, 3010 = ok но нужен ребут, 1638/5100 = уже стоит версия новее — тоже ок
  if "%VCRC%"=="0" (echo ok > "%~dp0.vcredist_ok") else if "%VCRC%"=="3010" (echo ok > "%~dp0.vcredist_ok") else if "%VCRC%"=="1638" (echo ok > "%~dp0.vcredist_ok") else if "%VCRC%"=="5100" (echo ok > "%~dp0.vcredist_ok") else (
    echo Visual C++ Redistributable не поставился ^(код %VCRC%^) — попробую ещё раз при следующем запуске.
  )
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
