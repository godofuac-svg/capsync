; Собирает CapSync-Setup.exe из папки package\ (должна лежать рядом с этим .nsi —
; см. BUILD_WINDOWS.md за тем, как её собрать: embeddable Python + wheels + ffmpeg +
; исходники). Запуск: makensis installer.nsi
;
; Установка БЕЗ выбора папки намеренно (нет "Page directory") — после того как
; инсталлятор один раз дал выбрать путь и получилось на синхронизируемый OneDrive
; "Рабочий стол", что ломало импорт torch (OneDrive подменяет файлы заглушками).
; %LOCALAPPDATA% вне зоны действия OneDrive Known Folder Move — фиксируем жёстко.
Unicode true
Name "CapSync"
OutFile "CapSync-Setup.exe"
InstallDir "$LOCALAPPDATA\CapSync"
RequestExecutionLevel user
; НЕ solid — соло-поток максимально жмёт, но распаковывается только последовательно
; целиком, из-за чего на ~1ГБ установка ощутимо дольше. Без /SOLID NSIS жмёт каждый
; файл отдельно — архив чуть крупнее, зато распаковка намного быстрее.
SetCompressor lzma
SetCompressorDictSize 32
ShowInstDetails show
Page instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "package\*.*"
  CreateShortcut "$DESKTOP\CapSync.lnk" "$INSTDIR\Start.bat" "" "" 0
  CreateDirectory "$SMPROGRAMS\CapSync"
  CreateShortcut "$SMPROGRAMS\CapSync\CapSync.lnk" "$INSTDIR\Start.bat" "" "" 0
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  Exec '"$INSTDIR\Start.bat"'
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\CapSync.lnk"
  RMDir /r "$SMPROGRAMS\CapSync"
  RMDir /r "$INSTDIR"
SectionEnd
