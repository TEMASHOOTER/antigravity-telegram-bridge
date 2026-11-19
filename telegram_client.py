"""
Асинхронный клиент Telegram Bot API на базе httpx.
Работает напрямую по протоколу Telegram Bot API (без тяжелых внешних фреймворков).
"""
import os
import asyncio
import httpx
from typing import Dict, Any, List, Optional

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

class TelegramClient:
    def __init__(self, token: str):
        self.token = token.strip()
        self.base_url = f"{TELEGRAM_API_BASE}{self.token}"
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        # Таймаут 45 секунд для поддержки Long Polling
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
        """Получает новые обновления через Long Polling."""
        url = f"{self.base_url}/getUpdates"
        params = {"offset": offset, "timeout": timeout}
        try:
            resp = await self.client.get(url, params=params)
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
        except httpx.RequestError as e:
            print(f"[Telegram Polling Warning]: {e}")
            await asyncio.sleep(2)
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
        Отправляет текстовое сообщение.
        Если текст превышает лимит Telegram (4096 символов), автоматически делит его на части.
        """
        url = f"{self.base_url}/sendMessage"
        
        # Разбиваем на фрагменты до 4000 символов
        chunk_size = 3900
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)] or [""]

        for i, chunk in enumerate(chunks):
            payload = {
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
                    # Если Telegram ругнулся на Markdown-форматирование, шлем без parse_mode
                    payload.pop("parse_mode", None)
                    await self.client.post(url, json=payload)
            except Exception as e:
                print(f"[Telegram Send Message Error]: {e}")
                return False
        return True

    async def send_photo(
        self,
        chat_id: int,
        photo_path: str,
        caption: Optional[str] = None
    ) -> bool:
        """Отправляет изображение в чат."""
        if not os.path.exists(photo_path):
            return False

        url = f"{self.base_url}/sendPhoto"
        try:
            await self.send_chat_action(chat_id, "upload_photo")
            with open(photo_path, "rb") as f:
                files = {"photo": (os.path.basename(photo_path), f, "image/png")}
                data = {"chat_id": chat_id}
                if caption:
                    data["caption"] = caption[:1024]
                resp = await self.client.post(url, data=data, files=files)
                return resp.json().get("ok", False)
        except Exception as e:
            print(f"[Telegram Send Photo Error]: {e}")
            return False
