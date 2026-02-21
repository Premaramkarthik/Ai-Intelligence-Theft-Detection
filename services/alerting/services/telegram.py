"""Telegram alert dispatcher."""
from __future__ import annotations

import aiohttp
from libs.shared.logging.logger import get_logger
from libs.shared.core.settings import get_settings

log = get_logger(__name__)

class TelegramService:
    def __init__(self) -> None:
        self._cfg = get_settings()

    async def send_alert(self, message: str) -> bool:
        if not self._cfg.telegram_token or not self._cfg.telegram_chat_id:
            log.warning("Telegram NOT configured")
            return False
        
        url = f"https://api.telegram.org/bot{self._cfg.telegram_token}/sendMessage"
        data = {"chat_id": self._cfg.telegram_chat_id, "text": message}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as resp:
                    return resp.status == 200
        except Exception as exc:
            log.error("Telegram send failed", extra={"error": str(exc)})
            return False
