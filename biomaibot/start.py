#!/usr/bin/env python3
"""
Telegram Bio Link & Abuse Detection Bot
Owner ID Setup Required!
"""

print("""
🔒 TELEGRAM BIO LINK DETECTION BOT
====================================

IMPORTANT SETUP:
1. Create .env file with:
   BOT_TOKEN=your_bot_token
   OWNER_ID=your_telegram_user_id
   LOG_CHANNEL_ID=your_log_channel_id
   GPT_API_KEY=your_openai_key
   SUPPORT_GROUP_ID=-100xxxxxxxxxx
   MONGO_URI=mongodb+srv://user:pass@host/dbname?retryWrites=true

2. Commands:
/status - Bot status
/setgptkey <key> - Update GPT key (Owner only)
/addspecial <user_id> - Add special user (Owner only)

3. Features:
   ✅ Link detection & deletion
   ✅ Bio monitoring 
   ✅ AI Abuse detection (GPT)
   ✅ Auto-delete edited messages (10s)
   ✅ Full logging
   ✅ Special privileges
""")

from bot_config import OWNER_ID
print(f"✅ Owner ID set: {OWNER_ID}")

if __name__ == "__main__":
    from main import BioLinkBot
    bot = BioLinkBot()
    bot.run()
