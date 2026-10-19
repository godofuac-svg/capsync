@echo off
setlocal enabledelayedexpansion
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
  set "VCRC=!ERRORLEVEL!"
  rem !...! — отложенная подстановка: без неё %VCRC% в этом же блоке подставился бы ДО
  rem выполнения set (то есть всегда пустой) и код ниже ВСЕГДА считал бы установку
  rem неудачной, даже если она реально прошла. Именно на этом мы и спотыкнулись.
  rem 0 = ok, 3010 = ok но нужен ребут, 1638/5100 = уже стоит версия новее — тоже ок
  if "!VCRC!"=="0" (echo ok > "%~dp0.vcredist_ok") else if "!VCRC!"=="3010" (echo ok > "%~dp0.vcredist_ok") else if "!VCRC!"=="1638" (echo ok > "%~dp0.vcredist_ok") else if "!VCRC!"=="5100" (echo ok > "%~dp0.vcredist_ok") else (
    echo Visual C++ Redistributable не поставился ^(код !VCRC!^) — попробую ещё раз при следующем запуске.
  )
)

:run
"%~dp0python\python.exe" -X utf8 run.py
rem exit 7 = run.py сам скачал обновление кода (core/selfupdate.py) в app_new\ —
rem подменяем лёгкие файлы поверх (python\ и ffmpeg\ там нет, тяжёлое не трогаем)
rem и перезапускаемся, без переотправки всего инсталлятора команде.
if errorlevel 8 goto done
if errorlevel 7 (
  if exist "%~dp0app_new" call :apply_update
  goto run
)
:done
if errorlevel 1 pause
exit /b

:apply_update
rem Python только что завершился — часть .py-модулей может на долю секунды ещё
rem держать файловый хендл (антивирус/индексатор тоже иногда подхватывают файл
rem сразу после записи). Без паузы+ретрая robocopy может ТИХО частично не
rem докопировать файлы — получится смесь старого и нового кода, и это выглядело
rem бы ровно как "обновление не применилось", без единой ошибки.
rem (goto-ретрай умышленно вынесен в отдельную call-подпрограмму — goto ВНУТРИ
rem скобочного if-блока в batch ненадёжен и может сломать разбор блока)
timeout /t 1 /nobreak >nul
set "RCATTEMPT=0"
:copyretry
robocopy "%~dp0app_new" "%~dp0" /E /NFL /NDL /NJH /NJS /NC /NS >nul
set "RC=%ERRORLEVEL%"
rem robocopy коды 0-7 — успех в разных формах (0=нечего копировать, 1=скопировано и т.д.),
rem 8+ — реальная ошибка (например, файл был занят)
if %RC% LSS 8 goto apply_update_done
set /a RCATTEMPT=%RCATTEMPT%+1
if %RCATTEMPT% LSS 5 (
  echo Обновление: файл занят, пробую ещё раз ^(%RCATTEMPT%/5^)...
  timeout /t 1 /nobreak >nul
  goto copyretry
)
echo ВНИМАНИЕ: не удалось полностью скопировать обновление ^(robocopy код %RC%^) —
echo код может быть частично старым. Останови CapSync и запусти Start.bat ещё раз.
:apply_update_done
rmdir /s /q "%~dp0app_new"
exit /b
