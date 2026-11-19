"""
Модуль взаимодействия с Antigravity.
Поддерживает два режима:
1. GUI Mode — находит открытое окно Antigravity IDE, переключается на него,
   вставляет текст через буфер обмена (с поддержкой любого Unicode/русского текста)
   и эмулирует нажатие Enter.
2. Agent Mode — программный вызов через Python SDK Antigravity (google-antigravity).
"""
import time
import os
import ctypes
from typing import Tuple, Optional, List

# Импорты win32
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


def list_matching_windows(keyword: str = "Antigravity") -> List[Tuple[int, str]]:
    """Возвращает список видимых окон, содержащих ключевое слово в заголовке."""
    if not WIN32_AVAILABLE:
        return []

    results = []
    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and keyword.lower() in title.lower():
                results.append((hwnd, title))
    win32gui.EnumWindows(enum_cb, None)
    return results


def set_clipboard_text(text: str) -> bool:
    """Копирует текст в буфер обмена Windows в формате Unicode."""
    if not WIN32_AVAILABLE:
        return False
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        print(f"[Clipboard error]: {e}")
        return False


def bring_window_to_front(hwnd: int):
    """Надежно выводит окно на передний план в Windows."""
    # Если окно свернуто, восстанавливаем
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    else:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

    # Обход ограничения Windows на SetForegroundWindow
    try:
        user32 = ctypes.windll.user32
        cur_thread = win32api.GetCurrentThreadId()
        fore_hwnd = win32gui.GetForegroundWindow()
        fore_thread, _ = win32process.GetWindowThreadProcessId(fore_hwnd)
        
        if cur_thread != fore_thread:
            user32.AttachThreadInput(cur_thread, fore_thread, True)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            user32.AttachThreadInput(cur_thread, fore_thread, False)
        else:
            win32gui.SetForegroundWindow(hwnd)
    except Exception:
        # Запасной метод через SwitchToThisWindow
        ctypes.windll.user32.SwitchToThisWindow(hwnd, True)


def simulate_paste_and_enter():
    """Эмулирует нажатие Ctrl+V и Enter."""
    time.sleep(0.3)
    # Зажимаем Ctrl
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    # Нажимаем V
    win32api.keybd_event(ord('V'), 0, 0, 0)
    time.sleep(0.05)
    # Отпускаем V
    win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
    # Отпускаем Ctrl
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
    
    time.sleep(0.2)
    # Нажимаем Enter (отправка сообщения в чат Antigravity)
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    time.sleep(0.05)
    # Отпускаем Enter
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

    windows = list_matching_windows(window_keyword)
    if not windows:
        # Пробуем более мягкий поиск
        windows = list_matching_windows("Gemini") or list_matching_windows("Code")

    if not windows:
        return False, f"❌ Окно со словом '{window_keyword}' не найдено на рабочем столе. Убедитесь, что Antigravity IDE запущена.", None

    hwnd, title = windows[0]
    
    # Копируем текст в буфер обмена
    if not set_clipboard_text(text):
        return False, "❌ Не удалось скопировать сообщение в буфер обмена.", None

    # Активируем окно
    bring_window_to_front(hwnd)
    time.sleep(0.3)

    # Вставляем и нажимаем Enter
    simulate_paste_and_enter()

    # Ждем указанную задержку, чтобы интерфейс начал печатать ответ
    screenshot_file = None
    if auto_screenshot:
        time.sleep(max(1.0, delay_after_send))
        screenshot_file = capture_screenshot("antigravity_reply.png")

    msg = f"✅ Сообщение отправлено в окно:\n`{title}`"
    return True, msg, screenshot_file


async def send_to_antigravity_agent(prompt: str) -> Tuple[bool, str]:
    """
    Вызов агента Antigravity через официальный Python SDK.
    """
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
