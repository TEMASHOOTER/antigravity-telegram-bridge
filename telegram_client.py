"""
Асинхронный клиент Telegram Bot API на базе httpx.
Работает напрямую по протоколу Telegram Bot API (без тяжелых внешних фреймворков).
"""
import os
import asyncio
import httpx
from typing import Dict, Any, List, Optional

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def split_message_chunks(text: str, max_len: int = 3850) -> List[str]:
    """
    Разбивает длинный текст на части до max_len символов:
    - Старается резать по границам строк (\n).
    - Аккуратно закрывает и переоткрывает блоки кода ``` на границе частей.
    """
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]

    chunks: List[str] = []
    remaining = text
    in_code_block = False

    while remaining:
        prefix = "```\n" if in_code_block else ""
        limit = max_len - len(prefix) - 10  # Запас под закрывающий ```

        if len(remaining) <= limit:
            chunk_body = remaining
            remaining = ""
        else:
            split_idx = remaining.rfind("\n", 0, limit)
            if split_idx <= 0:
                split_idx = limit
            chunk_body = remaining[:split_idx]
            remaining = remaining[split_idx:].lstrip("\n")

        # Считаем количество ``` внутри текущего фрагмента
        fence_count = chunk_body.count("```")
        will_stay_open = (fence_count % 2 == 1) ^ in_code_block

        chunk = prefix + chunk_body
        if will_stay_open:
            chunk += "\n```"

        chunks.append(chunk)
        in_code_block = will_stay_open

    return chunks


class TelegramClient:
    def __init__(self, token: str):
        self.token = token.strip()
        self.base_url = f"{TELEGRAM_API_BASE}{self.token}"
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def get_me(self) -> Dict[str, Any]:
        """Проверяет токен бота и возвращает информацию о нем."""
        url = f"{self.base_url}/getMe"
        resp = await self.client.get(url)
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(f"Ошибка токена Telegram: {data.get('description')}")
        return data.get("result", {})

    async def get_updates(self, offset: int = 0, timeout: int = 25) -> List[Dict[str, Any]]:
        """Получает новые обновления через Long Polling с устойчивой обработкой сбоев."""
        url = f"{self.base_url}/getUpdates"
        params = {"offset": offset, "timeout": timeout}
        try:
            resp = await self.client.get(url, params=params)
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
            err_code = data.get("error_code", resp.status_code)
            desc = data.get("description", "Unknown API error")
            print(f"[Telegram API Error {err_code}]: {desc}")
            await asyncio.sleep(3)
        except httpx.RequestError as e:
            print(f"[Telegram Polling Warning]: {e}")
            await asyncio.sleep(2)
        except (ValueError, KeyError) as e:
            print(f"[Telegram Invalid Response]: {e}")
            await asyncio.sleep(3)
        return []

    async def send_chat_action(self, chat_id: int, action: str = "typing"):
        """Показывает статус 'печатает...' или 'отправка фото' в чате."""
        url = f"{self.base_url}/sendChatAction"
        try:
            await self.client.post(url, json={"chat_id": chat_id, "action": action})
        except Exception:
            pass

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Отправляет текстовое сообщение с безопасным разбиением длинных ответов
        и откатом на обычный текст при ошибке Markdown.
        """
        url = f"{self.base_url}/sendMessage"
        chunks = split_message_chunks(text)

        for i, chunk in enumerate(chunks):
            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup and i == len(chunks) - 1:
                payload["reply_markup"] = reply_markup

            try:
                resp = await self.client.post(url, json=payload)
                data = resp.json()
                if not data.get("ok"):
                    payload.pop("parse_mode", None)
                    resp2 = await self.client.post(url, json=payload)
                    data2 = resp2.json()
                    if not data2.get("ok"):
                        print(f"[Telegram Send Message Error]: {data2.get('description')}")
                        return False
            except Exception as e:
                print(f"[Telegram Send Message Error]: {e}")
                return False
        return True

    async def send_photo(
        self,
        chat_id: int,
        photo_path: str,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown"
    ) -> bool:
        """Отправляет изображение в чат с поддержкой Markdown-подписи и fallback."""
        if not os.path.exists(photo_path):
            return False

        url = f"{self.base_url}/sendPhoto"
        try:
            await self.send_chat_action(chat_id, "upload_photo")
            with open(photo_path, "rb") as f:
                photo_bytes = f.read()

            filename = os.path.basename(photo_path)
            data: Dict[str, Any] = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = caption[:1024]
            if parse_mode and caption:
                data["parse_mode"] = parse_mode

            resp = await self.client.post(
                url,
                data=data,
                files={"photo": (filename, photo_bytes, "image/png")},
            )
            res_json = resp.json()
            if res_json.get("ok"):
                return True

            if "parse_mode" in data:
                data.pop("parse_mode")
                resp2 = await self.client.post(
                    url,
                    data=data,
                    files={"photo": (filename, photo_bytes, "image/png")},
                )
                res_json2 = resp2.json()
                if res_json2.get("ok"):
                    return True
                print(f"[Telegram Send Photo Error]: {res_json2.get('description')}")
            else:
                print(f"[Telegram Send Photo Error]: {res_json.get('description')}")
            return False
        except Exception as e:
            print(f"[Telegram Send Photo Error]: {e}")
            return False
