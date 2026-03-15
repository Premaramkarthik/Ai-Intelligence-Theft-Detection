"""
Telegram alert dispatcher using python-telegram-bot (v20+).

Uses `telegram.Bot` for async message sending with:
- Circuit breaker (CLOSED → OPEN after 5 failures, recovers after 30s)
- Exponential backoff retry (1s → 2s → 4s)
- Handles telegram.error.RetryAfter for flood control
- Formatted alert messages with emoji and markdown

Setup:
  1) Create bot via @BotFather → get TOKEN
  2) Get chat_id: https://api.telegram.org/bot<TOKEN>/getUpdates
  3) Set env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_IDS (comma-separated)
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime

from telegram import Bot
from telegram.error import RetryAfter, TimedOut, NetworkError

from shared.logging.logger import get_logger
from shared.core.settings import get_settings

log = get_logger(__name__)

MAX_FAILURES = 5
CIRCUIT_OPEN_DURATION_S = 30.0
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]


class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class TelegramService:
    """Sends shoplifting alerts to Telegram using python-telegram-bot."""

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._bot: Bot | None = None
        self._chat_ids: list[str] = []
        self._initialized = False
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

        token = self._cfg.telegram_bot_token
        if token:
            self._bot = Bot(token=token)
            log.info("Telegram Bot initialized")

        raw_ids = self._cfg.telegram_admin_chat_ids
        if raw_ids:
            self._chat_ids = [cid.strip() for cid in raw_ids.split(",") if cid.strip()]
            self._initialized = True
            log.info("Telegram chat IDs configured", extra={"count": len(self._chat_ids)})

    async def initialize(self) -> None:
        """Auto-discover chat IDs from getUpdates if none configured."""
        if self._initialized or not self._bot:
            return

        log.info("Auto-discovering Telegram chat IDs from getUpdates...")
        try:
            updates = await self._bot.get_updates(limit=20, timeout=5)
            seen: set[str] = set()
            for update in updates:
                chat = update.effective_chat
                if chat and str(chat.id) not in seen:
                    seen.add(str(chat.id))
                    name = chat.full_name or chat.title or "Unknown"
                    log.info("Discovered Telegram chat", extra={"id": chat.id, "name": name})

            if seen:
                self._chat_ids = list(seen)
                log.info("Auto-discovered chat IDs", extra={"count": len(self._chat_ids), "ids": self._chat_ids})
            else:
                log.warning("No chats found — send a message to the bot first")
        except Exception as e:
            log.error("Chat ID auto-discovery failed", extra={"error": str(e)})

        self._initialized = True

    def _is_circuit_open(self) -> bool:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= CIRCUIT_OPEN_DURATION_S:
                self._state = CircuitState.HALF_OPEN
                log.info("Telegram circuit → HALF_OPEN")
                return False
            return True
        return False

    def _record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            log.info("Telegram circuit → CLOSED (recovered)")
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= MAX_FAILURES:
            self._state = CircuitState.OPEN
            log.warning("Telegram circuit → OPEN", extra={"failures": self._failure_count})

    async def send_alert(self, message: str) -> bool:
        """Send alert to all configured chat IDs."""
        if not self._bot:
            log.warning("Telegram not configured (missing token)")
            return False

        # Auto-discover chat IDs on first call if needed
        if not self._initialized:
            await self.initialize()

        if not self._chat_ids:
            log.warning("No Telegram chat IDs available")
            return False

        if self._is_circuit_open():
            log.debug("Telegram circuit OPEN — skipping")
            return False

        success = False
        for chat_id in self._chat_ids:
            if await self._send_with_retry(chat_id, message):
                success = True

        if success:
            self._record_success()
        else:
            self._record_failure()

        return success

    async def send_shoplifting_alert(
        self,
        camera_id: str,
        confidence: float,
        timestamp: float | None = None,
    ) -> bool:
        """Send a formatted shoplifting alert."""
        ts = datetime.fromtimestamp(timestamp or time.time())
        msg = (
            "🚨 *SHOPLIFTING ALERT*\n\n"
            f"📹 Camera: `{camera_id}`\n"
            f"📊 Confidence: `{confidence:.1%}`\n"
            f"🕐 Time: `{ts.strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            "⚠️ Please review the live feed immediately."
        )
        return await self.send_alert(msg)

    async def _send_with_retry(self, chat_id: str, text: str) -> bool:
        """Send message with retry and flood control handling."""
        for attempt in range(MAX_RETRIES):
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown",
                    read_timeout=10,
                    write_timeout=10,
                )
                return True

            except RetryAfter as e:
                wait = e.retry_after
                log.warning("Telegram flood control", extra={"wait_s": wait, "chat_id": chat_id})
                await asyncio.sleep(wait)

            except (TimedOut, NetworkError) as e:
                log.warning("Telegram transient error", extra={
                    "error": str(e), "attempt": attempt + 1, "chat_id": chat_id,
                })
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

            except Exception as e:
                log.error("Telegram unexpected error", extra={"error": str(e), "chat_id": chat_id})
                break

        return False
