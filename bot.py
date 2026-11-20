"""
Главный исполняемый файл Antigravity Remote Bridge.
Запускает бота, слушает команды из Telegram и управляет Antigravity на ноутбуке.
"""
import os
import json
import asyncio
import sys
from typing import Dict, Any

# Обеспечиваем корректный вывод UTF-8 в консоль Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from telegram_client import TelegramClient
from system_tools import get_system_stats, capture_screenshot, execute_shell
from antigravity_bridge import (
    send_to_antigravity_gui,
    send_to_antigravity_agent,
    list_matching_windows,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        print(f"Файл {CONFIG_PATH} не найден. Создаем из шаблона...")
        default_config = {
            "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN_HERE",
            "allowed_chat_ids": [],
            "mode": "gui",
            "antigravity_window_title": "Antigravity",
            "auto_screenshot_after_send": True,
            "screenshot_delay_seconds": 2.0,
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        return default_config

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_main_keyboard() -> Dict[str, Any]:
    """Быстрые кнопки внизу клавиатуры для удобного управления со смартфона."""
    return {
        "keyboard": [
            [{"text": "📷 Скриншот экрана"}, {"text": "💻 Статус ноутбука"}],
            [{"text": "🔄 Сменить режим"}, {"text": "❓ Помощь"}],
        ],
        "resize_keyboard": True,
    }


def _safe_remove(path: str | None):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


async def handle_message(
    message: Dict[str, Any],
    client: TelegramClient,
    config: dict,
    state: Dict[str, Any],
):
    chat_id = message["chat"]["id"]
    user_id = message.get("from", {}).get("id", chat_id)
    user_name = message.get("from", {}).get("first_name", "User")

    # Запрещаем работу в групповых чатах/каналах в целях безопасности
    if chat_id != user_id:
        print(f"⚠️ Игнорирован запрос из группового чата {chat_id} от {user_name} ({user_id})")
        return

    allowed_ids = state["allowed_ids"]
    if allowed_ids and user_id not in allowed_ids:
        raw_text = (message.get("text") or "").strip()
        print(f"⚠️ Отклонен запрос от неавторизованного ID {user_id} ({user_name}): '{raw_text}'")
        await client.send_message(
            chat_id,
            f"⛔ *Доступ запрещен.*\nВаш Telegram ID: `{user_id}`.\n\n"
            "Добавьте этот ID в список `allowed_chat_ids` в файле `config.json` на ноутбуке.",
        )
        return

    if not allowed_ids:
        allowed_ids.add(user_id)
        config["allowed_chat_ids"] = list(allowed_ids)
        save_config(config)
        print(f"🔒 Авторизован первый пользователь: {user_name} (ID: {user_id}). Сохранено в config.json.")
        await client.send_message(
            chat_id,
            f"🎉 *Добро пожаловать, {user_name}!* Ваш ID `{user_id}` автоматически сохранен как владелец ноутбука.",
            reply_markup=get_main_keyboard(),
        )

    text = (message.get("text") or "").strip()
    if not text:
        await client.send_message(
            chat_id,
            "⚠️ Поддерживаются только текстовые сообщения и команды.",
            reply_markup=get_main_keyboard(),
        )
        return

    print(f"📩 [{user_name}]: {text}")
    current_mode = state["mode"]

    if text in ["/start", "/help", "❓ Помощь"]:
        help_msg = (
            "🤖 *Antigravity Remote Bridge*\n\n"
            f"📍 *Текущий режим:* `{current_mode.upper()}`\n\n"
            "*Как пользоваться:*\n"
            "• Просто отправьте любой текст или код — он мгновенно уйдет в Antigravity.\n"
            "• В режиме *GUI*: сообщение вставляется в окно Antigravity и жмется Enter, затем бот шлет скриншот ответа.\n"
            "• В режиме *AGENT*: запрос идет в Python SDK Antigravity.\n\n"
            "*Команды:*\n"
            "• `📷 Скриншот экрана` или `/screen` — снимок экрана ноутбука прямо сейчас\n"
            "• `💻 Статус ноутбука` или `/status` — батарея, CPU, RAM, диск\n"
            "• `🔄 Сменить режим` или `/mode [gui|agent]` — переключение режима\n"
            "• `/windows` — показать список открытых окон Antigravity/IDE\n"
            "• `/exec <команда>` — выполнить терминальную команду на ноутбуке"
        )
        await client.send_message(chat_id, help_msg, reply_markup=get_main_keyboard())

    elif text in ["/status", "💻 Статус ноутбука"]:
        stats = await asyncio.to_thread(get_system_stats)
        stats += f"\n\n⚙️ *Режим моста:* `{current_mode.upper()}`"
        await client.send_message(chat_id, stats, reply_markup=get_main_keyboard())

    elif text in ["/screen", "📷 Скриншот экрана"]:
        await client.send_chat_action(chat_id, "upload_photo")
        target_path = os.path.join(BASE_DIR, "current_screen.png")
        screen_path = await asyncio.to_thread(capture_screenshot, target_path)
        try:
            if screen_path and os.path.exists(screen_path):
                await client.send_photo(chat_id, screen_path, caption="🖥 Текущий экран ноутбука")
            else:
                await client.send_message(chat_id, "❌ Не удалось сделать скриншот экрана.")
        finally:
            _safe_remove(screen_path)

    elif text in ["/mode", "🔄 Сменить режим"] or text.startswith("/mode "):
        arg = text[6:].strip().lower() if text.startswith("/mode ") else ""
        if arg and arg not in ("gui", "agent"):
            await client.send_message(
                chat_id,
                "⚠️ Неизвестный режим. Используйте `/mode gui`, `/mode agent` или просто `/mode`.",
                reply_markup=get_main_keyboard(),
            )
            return

        new_mode = arg if arg else ("agent" if current_mode == "gui" else "gui")
        state["mode"] = new_mode
        config["mode"] = new_mode
        save_config(config)
        desc = (
            "Через окно Antigravity IDE (ввод текста + Enter)"
            if new_mode == "gui"
            else "Программный Python SDK"
        )
        await client.send_message(
            chat_id,
            f"🔄 Режим переключен на: *{new_mode.upper()}*\n({desc})",
            reply_markup=get_main_keyboard(),
        )

    elif text == "/windows":
        wins = (
            await asyncio.to_thread(list_matching_windows, "Antigravity")
            or await asyncio.to_thread(list_matching_windows, "Gemini")
            or await asyncio.to_thread(list_matching_windows, "Code")
        )
        if wins:
            list_str = "\n".join([f"• `{t}` (HWND: {h})" for h, t in wins])
            await client.send_message(chat_id, f"🪟 *Найденные окна IDE:*\n{list_str}")
        else:
            await client.send_message(chat_id, "❌ Окон Antigravity не обнаружено среди открытых программ.")

    elif text == "/exec":
        await client.send_message(
            chat_id,
            "ℹ️ Укажите команду после пробела, например:\n`/exec git status`",
        )

    elif text.startswith("/exec "):
        cmd = text[6:].strip()
        if not cmd:
            await client.send_message(chat_id, "ℹ️ Укажите команду после `/exec `. ")
            return
        await client.send_chat_action(chat_id, "typing")
        out = await asyncio.to_thread(execute_shell, cmd)
        safe_out = out.replace("```", "'''")
        await client.send_message(chat_id, f"💻 *Результат PowerShell:*\n```\n{safe_out}\n```")

    else:
        await client.send_chat_action(chat_id, "typing")

        if current_mode == "gui":
            ok, res_text, screen_file = await asyncio.to_thread(
                send_to_antigravity_gui,
                text,
                state["window_title"],
                state["auto_screen"],
                state["screen_delay"],
            )
            try:
                if ok and screen_file and os.path.exists(screen_file):
                    await client.send_photo(chat_id, screen_file, caption=res_text)
                else:
                    await client.send_message(chat_id, res_text)
            finally:
                _safe_remove(screen_file)
        else:
            ok, res_text = await send_to_antigravity_agent(text)
            await client.send_message(chat_id, res_text)


async def main(config: dict):
    token = config.get("telegram_bot_token", "").strip()
    state = {
        "allowed_ids": set(config.get("allowed_chat_ids", [])),
        "mode": config.get("mode", "gui"),
        "window_title": config.get("antigravity_window_title", "Antigravity"),
        "auto_screen": config.get("auto_screenshot_after_send", True),
        "screen_delay": config.get("screenshot_delay_seconds", 2.0),
    }

    print("\n" + "=" * 60)
    print("🚀 Antigravity Remote Bridge запускается...")
    print(f"Режим по умолчанию: {state['mode'].upper()}")
    print(f"Разрешенные User ID: {list(state['allowed_ids']) if state['allowed_ids'] else 'Все (первый написавший)'}")
    print("=" * 60)

    async with TelegramClient(token) as client:
        try:
            bot_info = await client.get_me()
            print(f"✅ Бот успешно подключен: @{bot_info.get('username')} ({bot_info.get('first_name')})")
            print("Ожидание сообщений с вашего телефона...\n")
        except Exception as e:
            print(f"❌ Не удалось подключиться к Telegram: {e}")
            return

        offset = 0

        while True:
            updates = await client.get_updates(offset=offset)
            for upd in updates:
                offset = upd["update_id"] + 1
                message = upd.get("message")
                if not message:
                    continue
                try:
                    await handle_message(message, client, config, state)
                except Exception as e:
                    print(f"[Ошибка обработки сообщения]: {e}")

            await asyncio.sleep(0.5)


if __name__ == "__main__":
    cfg = load_config()
    tok = cfg.get("telegram_bot_token", "").strip()

    if not tok or tok == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n" + "=" * 60)
        print("❌ ОШИБКА: Не указан токен Telegram-бота!")
        print("1. Откройте в Telegram бота @BotFather и создайте нового бота (/newbot).")
        print(f"2. Вставьте полученный токен в файл: {CONFIG_PATH}")
        print("=" * 60 + "\n")
        sys.exit(1)

    try:
        asyncio.run(main(cfg))
    except KeyboardInterrupt:
        print("\nБот остановлен пользователем.")
