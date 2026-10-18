"""
run.py — запуск CapSync. Поднимает FastAPI (uvicorn) в фоне и открывает
нативное окно (pywebview). Если pywebview недоступен — открывает в браузере.
"""
import os
import socket
import sys
import threading
import time
import webbrowser

HOST = os.environ.get("CAPSYNC_HOST", "127.0.0.1")


def _find_free_port(start_port: int, attempts: int = 20) -> int:
    """Порт может быть занят зависшим процессом от предыдущего запуска (двойной клик
    по Start.bat, старое окно не закрылось и т.п.) — вместо падения с "address already
    in use" просто ищем следующий свободный, как делает большинство dev-серверов."""
    for port in range(start_port, start_port + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Не нашлось свободного порта в диапазоне {start_port}-{start_port + attempts}")


PORT = _find_free_port(int(os.environ.get("CAPSYNC_PORT", "8877")))
URL = f"http://{HOST}:{PORT}"


def _serve():
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, log_level="warning")


def _wait(timeout=25.0):
    for _ in range(int(timeout * 10)):
        try:
            with socket.create_connection((HOST, PORT), 0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _storage_path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        return os.path.join(base, "CapSync")
    return os.path.expanduser("~/Library/Application Support/CapSync")


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from core import selfupdate
    if selfupdate.check_and_apply():
        print("✓ Обновление загружено — перезапускаюсь…")
        sys.exit(7)  # launch.command/Start.bat подменит файлы из app_new/ и перезапустит

    threading.Thread(target=_serve, daemon=True).start()
    if not _wait():
        print("✗ сервер не поднялся")
        sys.exit(1)
    print(f"✓ CapSync: {URL}")
    try:
        import webview

        class Api:
            """Мост в нативные диалоги ОС — зовётся из JS как window.pywebview.api.<метод>().
            Нужен конкретно для выбора папки CapCut руками (вместо ручного ввода пути)."""
            def __init__(self):
                self._window = None

            def pick_folder(self):
                result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
                return result[0] if result else None

        api = Api()
        window = webview.create_window("CapSync — FMB Team", URL, width=1180, height=820, min_size=(960, 640),
                                        background_color="#0A0A0C", js_api=api)
        api._window = window
        try:
            webview.start(private_mode=False, storage_path=_storage_path())
        except TypeError:
            webview.start()
    except Exception as e:
        print(f"(нативное окно недоступно: {e}) — открываю в браузере")
        webbrowser.open(URL)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nпока")


if __name__ == "__main__":
    main()
