#!/usr/bin/env python3
"""
Test Telegram alert sending.

Usage:
  1. Get a token from @BotFather
  2. Send ANY message to your bot first (so getUpdates has a chat)
  3. Run:  TELEGRAM_BOT_TOKEN='your_token' python tests/test_telegram_alert.py

The script auto-discovers your chat ID from getUpdates — no manual lookup needed.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot


async def auto_discover_chat_id(bot: Bot) -> str | None:
    """Fetch chat ID automatically from getUpdates."""
    print("🔍 Auto-discovering chat ID from getUpdates...")
    try:
        updates = await bot.get_updates(limit=10, timeout=5)
        if not updates:
            print("❌ No updates found. Please send a message to your bot first, then re-run.")
            return None

        # Get the most recent chat ID
        chat_id = str(updates[-1].effective_chat.id)
        chat_name = (
            updates[-1].effective_chat.full_name
            or updates[-1].effective_chat.title
            or "Unknown"
        )
        print(f"✅ Found chat: {chat_name} (ID: {chat_id})")
        return chat_id
    except Exception as e:
        print(f"❌ getUpdates failed: {e}")
        return None


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "8351386436:AAFUV5TB9J86LIwcZzzS26m-3Ib7n-mGxco")

    if not token:
        print("❌ Please set TELEGRAM_BOT_TOKEN")
        print()
        print("Steps:")
        print("  1. Talk to @BotFather on Telegram → /newbot → get TOKEN")
        print("  2. Send any message to your new bot")
        print("  3. Run:")
        print("     TELEGRAM_BOT_TOKEN='your_token' python tests/test_telegram_alert.py")
        return

    bot = Bot(token=token)

    # Auto-discover or use provided chat ID
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        chat_id = await auto_discover_chat_id(bot)
        if not chat_id:
            return

    # Test 1: Simple message
    print("\n📤 Test 1: Sending simple message...")
    try:
        msg = await bot.send_message(chat_id=chat_id, text="✅ Pipeline OpenCV — connection test")
        print(f"   ✅ Sent! (msg_id: {msg.message_id})")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return

    # Test 2: Formatted shoplifting alert
    print("📤 Test 2: Sending formatted shoplifting alert...")
    alert_text = (
        "🚨 *SHOPLIFTING ALERT*\n\n"
        "📹 Camera: `cam_01`\n"
        "📊 Confidence: `87.3%`\n"
        "🕐 Time: `2026-03-04 06:30:00`\n\n"
        "⚠️ Please review the live feed immediately."
    )
    try:
        msg = await bot.send_message(chat_id=chat_id, text=alert_text, parse_mode="Markdown")
        print(f"   ✅ Sent! (msg_id: {msg.message_id})")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return

    print(f"\n🎉 All tests passed! Chat ID: {chat_id}")
    print(f"   Add to .env: TELEGRAM_BOT_TOKEN={token}")
    print(f"                TELEGRAM_CHAT_ID={chat_id}")


if __name__ == "__main__":
    asyncio.run(main())
