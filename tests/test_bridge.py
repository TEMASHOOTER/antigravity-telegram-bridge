import os
import sys
import json
import re
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import bot
import antigravity_bridge
import telegram_client
import system_tools


def run_coro_sync(coro):
    """Исполняет корутину с синхронными моками без запуска сетевых сокетов ОС."""
    try:
        while True:
            coro.send(None)
    except StopIteration as exc:
        return exc.value


class TestRepoIntegrity(unittest.TestCase):
    def test_readme_links_exist(self):
        readme_path = os.path.join(PROJECT_DIR, "README.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        md_links = re.findall(r'\[[^\]]+\]\(([^)#]+)\)', content)
        html_hrefs = re.findall(r'href="([^"#]+)"', content)
        html_srcs = re.findall(r'src="([^"#]+)"', content)

        all_local = [
            t for t in (md_links + html_hrefs + html_srcs)
            if not t.startswith(("http://", "https://"))
        ]
        missing = [
            t for t in all_local
            if not os.path.exists(os.path.join(PROJECT_DIR, t.replace("/", os.sep)))
        ]
        self.assertEqual(missing, [], f"Broken local links in README.md: {missing}")

    def test_config_example_valid(self):
        path = os.path.join(PROJECT_DIR, "config.example.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("telegram_bot_token", data)
        self.assertEqual(data["allowed_chat_ids"], [])

    def test_gitignore_protects_secrets(self):
        path = os.path.join(PROJECT_DIR, ".gitignore")
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        self.assertIn("config.json", lines)
        self.assertIn("*.png", lines)


class TestAntigravityBridge(unittest.TestCase):
    def test_window_collision_with_run_bat_and_browser(self):
        fake_windows = {
            101: ("Antigravity Remote Bridge", "cmd.exe"),
            102: ("TEMASHOOTER/antigravity-telegram-bridge - Google Chrome", "chrome.exe"),
            103: ("my-project - Antigravity IDE", "antigravity ide.exe"),
        }

        def fake_enum(cb, extra):
            for hwnd in fake_windows:
                cb(hwnd, extra)

        with patch.object(antigravity_bridge.win32gui, "IsWindowVisible", return_value=True), \
             patch.object(antigravity_bridge.win32gui, "EnumWindows", side_effect=fake_enum), \
             patch.object(antigravity_bridge.win32gui, "GetWindowText", side_effect=lambda h: fake_windows[h][0]), \
             patch.object(antigravity_bridge, "_get_process_name", side_effect=lambda h: fake_windows[h][1]):
            matches = antigravity_bridge.list_matching_windows("Antigravity")
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0], (103, "my-project - Antigravity IDE"))

    def test_clipboard_closed_on_exception(self):
        with patch.object(antigravity_bridge.win32clipboard, "OpenClipboard") as mock_open, \
             patch.object(antigravity_bridge.win32clipboard, "EmptyClipboard"), \
             patch.object(antigravity_bridge.win32clipboard, "SetClipboardText", side_effect=RuntimeError("Clipboard error")), \
             patch.object(antigravity_bridge.win32clipboard, "CloseClipboard") as mock_close, \
             patch.object(antigravity_bridge.time, "sleep"):
            res = antigravity_bridge.set_clipboard_text("hello")
            self.assertFalse(res)
            self.assertEqual(mock_open.call_count, 5)
            self.assertEqual(mock_close.call_count, 5)

    def test_empty_text_rejected_before_clipboard(self):
        with patch.object(antigravity_bridge, "list_matching_windows", return_value=[(103, "Antigravity IDE")]), \
             patch.object(antigravity_bridge, "set_clipboard_text") as mock_clip:
            ok, msg, _ = antigravity_bridge.send_to_antigravity_gui("   ", auto_screenshot=False)
            self.assertFalse(ok)
            self.assertIn("пустое", msg)
            mock_clip.assert_not_called()

    def test_locked_screen_detected(self):
        with patch.object(antigravity_bridge, "is_workstation_locked", return_value=True):
            ok, msg, _ = antigravity_bridge.send_to_antigravity_gui("hello", auto_screenshot=False)
            self.assertFalse(ok)
            self.assertIn("заблокирован", msg)

    def test_bring_window_to_front_zero_foreground(self):
        with patch.object(antigravity_bridge.win32gui, "IsIconic", return_value=False), \
             patch.object(antigravity_bridge.win32gui, "ShowWindow"), \
             patch.object(antigravity_bridge.win32gui, "GetForegroundWindow", return_value=0), \
             patch.object(antigravity_bridge.win32gui, "SetForegroundWindow") as mock_fg, \
             patch.object(antigravity_bridge.win32gui, "BringWindowToTop"):
            antigravity_bridge.bring_window_to_front(12345)
            mock_fg.assert_called_once_with(12345)


class TestTelegramClient(unittest.TestCase):
    def test_get_updates_handles_non_json_502(self):
        async def run():
            tc = telegram_client.TelegramClient("123:ABC")
            tc.client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 502
            mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "<html>502</html>", 0)
            tc.client.get = AsyncMock(return_value=mock_resp)
            with patch.object(telegram_client.asyncio, "sleep", new=AsyncMock()):
                updates = await tc.get_updates()
            self.assertEqual(updates, [])

        run_coro_sync(run())

    def test_get_updates_logs_409_conflict(self):
        async def run():
            tc = telegram_client.TelegramClient("123:ABC")
            tc.client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 409
            mock_resp.json.return_value = {"ok": False, "error_code": 409, "description": "Conflict"}
            tc.client.get = AsyncMock(return_value=mock_resp)
            with patch.object(telegram_client.asyncio, "sleep", new=AsyncMock()), \
                 patch("builtins.print") as mock_print:
                updates = await tc.get_updates()
            self.assertEqual(updates, [])
            mock_print.assert_called()

        run_coro_sync(run())

    def test_send_message_chunking_markdown_safety(self):
        async def run():
            tc = telegram_client.TelegramClient("123:ABC")
            tc.client = MagicMock()
            sent_payloads = []

            async def fake_post(url, json=None, **kwargs):
                sent_payloads.append(json)
                m = MagicMock()
                m.json.return_value = {"ok": True}
                return m

            tc.client.post = fake_post
            long_code = "```\n" + ("x = 1\n" * 1000) + "```"
            ok = await tc.send_message(123, long_code)
            self.assertTrue(ok)
            self.assertGreater(len(sent_payloads), 1)
            for p in sent_payloads:
                self.assertEqual(p["text"].count("```") % 2, 0)

        run_coro_sync(run())


class TestSystemTools(unittest.TestCase):
    def test_get_system_stats(self):
        stats = system_tools.get_system_stats()
        self.assertIn("CPU:", stats)
        self.assertIn("RAM:", stats)

    def test_decode_shell_output_mixed_utf8_and_cp866(self):
        raw = "Привет UTF8\n".encode("utf-8") + "Подключение по локальной сети\n".encode("cp866")
        decoded = system_tools.decode_shell_output(raw)
        self.assertIn("Привет UTF8", decoded)
        if os.name == "nt":
            self.assertIn("Подключение по локальной сети", decoded)

    def test_execute_shell_timeout(self):
        out = system_tools.execute_shell("Start-Sleep -Seconds 3", timeout=1)
        self.assertIn("Превышено время ожидания", out)

    def test_screenshot_path_with_quote_escaping_and_dpi(self):
        with patch("subprocess.run") as mock_run, \
             patch.dict(sys.modules, {"PIL": None, "PIL.ImageGrab": None}):
            mock_run.return_value = MagicMock(stderr=b"")
            system_tools.capture_screenshot("bad'path.png")
            ps_cmd = mock_run.call_args[0][0][3]
            self.assertIn("bad''path.png", ps_cmd)
            self.assertIn("SetProcessDPIAware", ps_cmd)


class TestBotHandlers(unittest.TestCase):
    def _make_state(self, allowed=None, mode="gui"):
        return {
            "allowed_ids": set(allowed or [100]),
            "mode": mode,
            "window_title": "Antigravity",
            "auto_screen": False,
            "screen_delay": 1.0,
        }

    def test_non_text_message_not_forwarded_to_gui(self):
        client = MagicMock()
        client.send_message = AsyncMock(return_value=True)
        state = self._make_state()
        msg = {"chat": {"id": 100}, "from": {"id": 100, "first_name": "Artem"}, "sticker": {"file_id": "x"}}

        with patch.object(bot, "send_to_antigravity_gui") as mock_gui:
            run_coro_sync(bot.handle_message(msg, client, {}, state))
            mock_gui.assert_not_called()
            client.send_message.assert_awaited_once()
            self.assertIn("только текстовые", client.send_message.call_args[0][1])

    def test_exec_without_args_handled(self):
        client = MagicMock()
        client.send_message = AsyncMock(return_value=True)
        state = self._make_state()
        msg = {"chat": {"id": 100}, "from": {"id": 100, "first_name": "Artem"}, "text": "/exec"}

        with patch.object(bot, "send_to_antigravity_gui") as mock_gui:
            run_coro_sync(bot.handle_message(msg, client, {}, state))
            mock_gui.assert_not_called()
            self.assertIn("Укажите команду", client.send_message.call_args[0][1])

    def test_mode_with_args_handled(self):
        client = MagicMock()
        client.send_message = AsyncMock(return_value=True)
        state = self._make_state(mode="gui")
        config = {"mode": "gui"}
        msg = {"chat": {"id": 100}, "from": {"id": 100, "first_name": "Artem"}, "text": "/mode agent"}

        with patch.object(bot, "save_config") as mock_save:
            run_coro_sync(bot.handle_message(msg, client, config, state))
            self.assertEqual(state["mode"], "agent")
            self.assertEqual(config["mode"], "agent")
            mock_save.assert_called_once()

    def test_group_chat_rejected(self):
        client = MagicMock()
        client.send_message = AsyncMock(return_value=True)
        state = self._make_state()
        msg = {"chat": {"id": -555}, "from": {"id": 100, "first_name": "Artem"}, "text": "/status"}

        run_coro_sync(bot.handle_message(msg, client, {}, state))
        client.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
