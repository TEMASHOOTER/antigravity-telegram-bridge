"""
Модуль взаимодействия с Antigravity.
Поддерживает два режима:
1. GUI Mode — находит открытое окно Antigravity IDE (исключая консоль самого бота и браузеры),
   переключается на него, вставляет текст через буфер обмена (Unicode) и нажимает Enter.
2. Agent Mode — программный вызов через Python SDK Antigravity (google-antigravity).
"""
import time
import os
import ctypes
from typing import Tuple, Optional, List
import psutil

try:
    import win32gui
    import win32con
    import win32api
    import win32process
    import win32clipboard
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

from system_tools import capture_screenshot

IGNORED_PROCESSES = {
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "windowsterminal.exe",
    "conhost.exe",
    "python.exe",
    "pythonw.exe",
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "opera.exe",
    "brave.exe",
    "browser.exe",
}


def _get_process_name(hwnd: int) -> str:
    """Возвращает имя процесса (в нижнем регистре), которому принадлежит окно."""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid:
            return psutil.Process(pid).name().lower()
    except Exception:
        pass
    return ""


def is_workstation_locked() -> bool:
    """Проверяет, заблокирован ли экран Windows (активен ли LogonUI.exe)."""
    try:
        for proc in psutil.process_iter(["name"]):
            name = proc.info.get("name")
            if name and name.lower() == "logonui.exe":
                return True
    except Exception:
        pass
    return False


def list_matching_windows(
    keyword: str = "Antigravity",
    exclude_non_ide: bool = True
) -> List[Tuple[int, str]]:
    """
    Возвращает список видимых окон IDE, содержащих ключевое слово в заголовке.
    Исключает окно консоли самого бота, терминалы и браузеры (при exclude_non_ide=True).
    """
    if not WIN32_AVAILABLE:
        return []

    try:
        self_console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    except Exception:
        self_console_hwnd = 0

    ide_matches: List[Tuple[int, str]] = []
    other_matches: List[Tuple[int, str]] = []

    def enum_cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if self_console_hwnd and hwnd == self_console_hwnd:
            return

        title = win32gui.GetWindowText(hwnd)
        if not title or keyword.lower() not in title.lower():
            return

        if exclude_non_ide and "antigravity remote bridge" in title.lower():
            return

        proc_name = _get_process_name(hwnd)
        if exclude_non_ide and proc_name in IGNORED_PROCESSES:
            return

        if any(k in proc_name for k in ("antigravity", "code", "cursor")):
            ide_matches.append((hwnd, title))
        else:
            other_matches.append((hwnd, title))

    win32gui.EnumWindows(enum_cb, None)
    return ide_matches + other_matches


def set_clipboard_text(text: str) -> bool:
    """Надежно копирует текст в буфер обмена Windows в формате Unicode."""
    if not WIN32_AVAILABLE or not text:
        return False

    for attempt in range(5):
        opened = False
        try:
            win32clipboard.OpenClipboard()
            opened = True
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            return True
        except Exception as e:
            if attempt == 4:
                print(f"[Clipboard error]: {e}")
                return False
            time.sleep(0.05)
        finally:
            if opened:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
    return False


def bring_window_to_front(hwnd: int):
    """Надежно выводит окно на передний план в Windows."""
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    else:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

    try:
        user32 = ctypes.windll.user32
        cur_thread = win32api.GetCurrentThreadId()
        fore_hwnd = win32gui.GetForegroundWindow()
        fore_thread = 0
        if fore_hwnd:
            fore_thread, _ = win32process.GetWindowThreadProcessId(fore_hwnd)

        attached = False
        if fore_thread and cur_thread != fore_thread:
            attached = bool(user32.AttachThreadInput(cur_thread, fore_thread, True))
        try:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(cur_thread, fore_thread, False)
    except Exception:
        ctypes.windll.user32.SwitchToThisWindow(hwnd, True)


def simulate_paste_and_enter():
    """Эмулирует нажатие Ctrl+V и Enter."""
    time.sleep(0.3)
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord("V"), 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

    time.sleep(0.2)
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)


def send_to_antigravity_gui(
    text: str,
    window_keyword: str = "Antigravity",
    auto_screenshot: bool = True,
    delay_after_send: float = 2.0
) -> Tuple[bool, str, Optional[str]]:
    """
    Отправляет текст в открытое окно Antigravity IDE и делает контрольный скриншот.
    Возвращает (успех, текстовое_сообщение, путь_к_скриншоту).
    """
    if not WIN32_AVAILABLE:
        return False, "Библиотека pywin32 не доступна на этой машине.", None

    if not text or not text.strip():
        return False, "⚠️ Нельзя отправить пустое сообщение в Antigravity.", None

    if is_workstation_locked():
        return False, (
            "🔒 Экран ноутбука заблокирован (Win+L). "
            "Windows блокирует ввод текста в окна на заблокированном экране."
        ), None

    windows = list_matching_windows(window_keyword)
    if not windows:
        windows = list_matching_windows("Gemini") or list_matching_windows("Code")

    if not windows:
        return False, (
            f"❌ Окно со словом '{window_keyword}' не найдено на рабочем столе. "
            "Убедитесь, что Antigravity IDE запущена."
        ), None

    hwnd, title = windows[0]

    if not set_clipboard_text(text):
        return False, "❌ Не удалось скопировать сообщение в буфер обмена.", None

    bring_window_to_front(hwnd)
    time.sleep(0.3)
    simulate_paste_and_enter()

    screenshot_file = None
    if auto_screenshot:
        time.sleep(max(1.0, delay_after_send))
        reply_screen_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "antigravity_reply.png"
        )
        screenshot_file = capture_screenshot(reply_screen_path)

    msg = f"✅ Сообщение отправлено в окно:\n`{title}`"
    return True, msg, screenshot_file


async def send_to_antigravity_agent(prompt: str) -> Tuple[bool, str]:
    """
    Вызов агента Antigravity через официальный Python SDK.
    """
    if not prompt or not prompt.strip():
        return False, "⚠️ Запрос не может быть пустым."

    try:
        from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
    except ImportError:
        return False, (
            "⚠️ Пакет `google-antigravity` еще не установлен на этом ноутбуке.\n\n"
            "Вы можете:\n"
            "1. Переключиться на режим окна: `/mode gui`\n"
            "2. Или установить SDK командой в консоли: `pip install google-antigravity`"
        )

    try:
        config = LocalAgentConfig(
            system_instructions="Ты полезный ассистент разработки. Отвечай кратко и емко.",
            capabilities=CapabilitiesConfig()
        )
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            full_text = ""
            async for token in response:
                full_text += token
            return True, full_text or "Агент выполнил задачу без текстового вывода."
    except Exception as e:
        return False, f"❌ Ошибка вызова агента SDK: {str(e)}"
