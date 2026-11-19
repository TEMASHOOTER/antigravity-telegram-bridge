"""
Главный исполняемый файл Antigravity Remote Bridge.
Запускает бота, слушает команды из Telegram и управляет Antigravity на ноутбуке.
"""
import os
import json
import asyncio
import sys

# Обеспечиваем корректный вывод UTF-8 в консоль Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from telegram_client import TelegramClient
from system_tools import get_system_stats, capture_screenshot, execute_shell
from antigravity_bridge import send_to_antigravity_gui, send_to_antigravity_agent, list_matching_windows

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        print(f"Файл {CONFIG_PATH} не найден. Создаем из шаблона...")
        default_config = {
            "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN_HERE",
            "allowed_chat_ids": [],
            "mode": "gui",
            "antigravity_window_title": "Antigravity",
            "auto_screenshot_after_send": True,
            "screenshot_delay_seconds": 2.0
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        return default_config

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_main_keyboard():
    """Быстрые кнопки внизу клавиатуры для удобного управления со смартфона."""
    return {
        "keyboard": [
            [{"text": "📷 Скриншот экрана"}, {"text": "💻 Статус ноутбука"}],
            [{"text": "🔄 Сменить режим"}, {"text": "❓ Помощь"}]
        ],
        "resize_keyboard": True
    }


async def main(config: dict):
    token = config.get("telegram_bot_token", "").strip()
    allowed_ids = set(config.get("allowed_chat_ids", []))
    current_mode = config.get("mode", "gui")
    window_title = config.get("antigravity_window_title", "Antigravity")
    auto_screen = config.get("auto_screenshot_after_send", True)
    screen_delay = config.get("screenshot_delay_seconds", 2.0)

    print("\n" + "=" * 60)
    print("🚀 Antigravity Remote Bridge запускается...")
    print(f"Режим по умолчанию: {current_mode.upper()}")
    print(f"Разрешенные User/Chat ID: {list(allowed_ids) if allowed_ids else 'Все (первый написавший)'}")
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

                chat_id = message["chat"]["id"]
                user_id = message.get("from", {}).get("id", chat_id)
                user_name = message.get("from", {}).get("first_name", "User")
                text = message.get("text", "").strip()

                # Проверка авторизации
                if allowed_ids and user_id not in allowed_ids:
                    print(f"⚠️ Отклонен запрос от неавторизованного ID {user_id} ({user_name}): '{text}'")
                    await client.send_message(
                        chat_id,
                        f"⛔ *Доступ запрещен.*\nВаш Telegram ID: `{user_id}`.\n\n"
                        f"Добавьте этот ID в список `allowed_chat_ids` в файле `config.json` на ноутбуке."
                    )
                    continue

                # Если список пуст — привязываем первого написавшего пользователя
                if not allowed_ids:
                    allowed_ids.add(user_id)
                    config["allowed_chat_ids"] = list(allowed_ids)
                    save_config(config)
                    print(f"🔒 Авторизован первый пользователь: {user_name} (ID: {user_id}). Сохранено в config.json.")
                    await client.send_message(
                        chat_id,
                        f"🎉 *Добро пожаловать, {user_name}!* Ваш ID `{user_id}` автоматически сохранен как владелец ноутбука.",
                        reply_markup=get_main_keyboard()
                    )

                print(f"📩 [{user_name}]: {text}")

                # Обработка команд
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
                        "• `🔄 Сменить режим` или `/mode` — переключение между GUI и AGENT\n"
                        "• `/windows` — показать список открытых окон Antigravity/IDE\n"
                        "• `/exec <команда>` — выполнить терминальную команду на ноутбуке"
                    )
                    await client.send_message(chat_id, help_msg, reply_markup=get_main_keyboard())

                elif text in ["/status", "💻 Статус ноутбука"]:
                    stats = get_system_stats()
                    stats += f"\n\n⚙️ *Режим моста:* `{current_mode.upper()}`"
                    await client.send_message(chat_id, stats, reply_markup=get_main_keyboard())

                elif text in ["/screen", "📷 Скриншот экрана"]:
                    await client.send_chat_action(chat_id, "upload_photo")
                    screen_path = capture_screenshot("current_screen.png")
                    if screen_path and os.path.exists(screen_path):
                        await client.send_photo(chat_id, screen_path, caption="🖥 Текущий экран ноутбука")
                    else:
                        await client.send_message(chat_id, "❌ Не удалось сделать скриншот экрана.")

                elif text in ["/mode", "🔄 Сменить режим"]:
                    current_mode = "agent" if current_mode == "gui" else "gui"
                    config["mode"] = current_mode
                    save_config(config)
                    desc = "Через окно Antigravity IDE (ввод текста + Enter)" if current_mode == "gui" else "Программный Python SDK"
                    await client.send_message(
                        chat_id,
                        f"🔄 Режим переключен на: *{current_mode.upper()}*\n({desc})",
                        reply_markup=get_main_keyboard()
                    )

                elif text == "/windows":
                    wins = list_matching_windows("Antigravity") or list_matching_windows("Code") or list_matching_windows("Gemini")
                    if wins:
                        list_str = "\n".join([f"• `{t}` (HWND: {h})" for h, t in wins])
                        await client.send_message(chat_id, f"🪟 *Найденные окна:*\n{list_str}")
                    else:
                        await client.send_message(chat_id, "❌ Окон Antigravity не обнаружено среди открытых программ.")

                elif text.startswith("/exec "):
                    cmd = text[6:].strip()
                    await client.send_chat_action(chat_id, "typing")
                    out = execute_shell(cmd)
                    await client.send_message(chat_id, f"💻 *Результат `powershell`:*\n```\n{out}\n```")

                else:
                    # Обычное текстовое сообщение -> отправка в Antigravity
                    await client.send_chat_action(chat_id, "typing")

                    if current_mode == "gui":
                        ok, res_text, screen_file = send_to_antigravity_gui(
                            text=text,
                            window_keyword=window_title,
                            auto_screenshot=auto_screen,
                            delay_after_send=screen_delay
                        )
                        if ok:
                            if screen_file and os.path.exists(screen_file):
                                await client.send_photo(chat_id, screen_file, caption=res_text)
                            else:
                                await client.send_message(chat_id, res_text)
                        else:
                            await client.send_message(chat_id, res_text)

                    else:
                        # Agent SDK режим
                        ok, res_text = await send_to_antigravity_agent(text)
                        await client.send_message(chat_id, res_text)

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
