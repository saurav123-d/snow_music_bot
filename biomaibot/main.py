import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, ChatMemberHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import Conflict, NetworkError
import re
from bot_config import *
from abuse import AbuseDetector
from bio import BioLinkDetector
from help import register_help_commands
from storage import Storage

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class BioLinkBot:
    def __init__(self):
        self.abuse_detector = AbuseDetector()
        self.edited_messages = {}  # {chat_id: {message_id: timestamp}}
        self.special_users = set(SPECIAL_USERS)
        self.delete_tasks = {}
        self.bio_detector = BioLinkDetector()
        self.blocklist = set()
        self.link_whitelist = set()
        self.media_delete_delay = MEDIA_DELETE_DELAY
        self.sticker_delete_delay = STICKER_DELETE_DELAY
        self.storage = Storage()
        self.chat_delays = {}  # {chat_id: {"media": int|None, "sticker": int|None}}
        self._load_persistent_state()
    
    async def send_log(self, context: ContextTypes.DEFAULT_TYPE, log_message: str, user_info: str = ""):
        """Send log to log channel"""
        try:
            import html
            safe_log = html.escape(log_message)
            safe_user = html.escape(user_info)
            
            log_text = f"""
🔒 <b>Bot Action Log</b>
🕐 <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>
👤 {safe_user}
📝 {safe_log}
            """
            await context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=log_text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send log: {e}")
    
    def message_has_link(self, message) -> bool:
        return self.bio_detector.has_link_in_message(message)
    
    async def check_user_bio(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str = None):
        """Check user bio for links"""
        try:
            chat_member = await context.bot.get_chat_member(chat_id=context.job.chat_id, user_id=user_id)
            user = chat_member.user
            
            if username:
                profile_photos = await context.bot.get_user_profile_photos(user_id, limit=1)
                if profile_photos.total_count > 0:
                    # Bio link detection (this is advanced, requires manual checking or API)
                    pass
            
            # Log bio check
            await self.send_log(context, f"🔍 Bio checked for @{username or user_id}", 
                              f"User: {user.full_name} (@{username or 'no_username'})")
            
        except Exception as e:
            logger.error(f"Bio check error: {e}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new messages"""
        message = update.message
        chat_id = message.chat.id
        user_id = message.from_user.id
        user = message.from_user
        self.storage.save_event("seen", {"chat_id": chat_id, "user_id": user_id})
        
        is_special = user_id in self.special_users or user_id == OWNER_ID
        
        text = message.text or message.caption or ""
        
        # Blocklist detection first
        if text and self.contains_blocked(text):
            try:
                await message.delete()
                await self.send_log(context, f"🚫 Blocklist word deleted", 
                                  f"User: {user.full_name} (@{user.username or 'no_username'})")
                self.storage.save_event("blocklist_delete", {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "text": text
                })
                return
            except:
                pass
        
        if self.message_has_link(message) and not self.is_whitelisted(message):
            try:
                await message.delete()
                reason = self.bio_detector.get_link_reason(message) or "unknown"
                await self.send_log(context, f"🗑️ Link message deleted", 
                                  f"User: {user.full_name} (@{user.username or 'no_username'})\nReason: {reason}")
                self.storage.save_event("link_delete", {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "text": text,
                    "reason": reason
                })
                return
            except Exception as e:
                logger.error(f"Failed to delete link message: {e}")
                await self.send_log(context, f"❌ Failed to delete link message: {e}", 
                                  f"User: {user.full_name} (@{user.username or 'no_username'})")
        
        # 2. Abuse detection
        if ABUSE_DETECTION_ENABLED:
            abuse_result = await self.abuse_detector.detect_abuse(text)
            if abuse_result["is_abusive"] and abuse_result["confidence"] >= ABUSE_THRESHOLD:
                try:
                    await message.delete()
                    await self.send_log(context, f"🚫 Abusive content deleted", 
                                      f"User: {user.full_name} (@{user.username or 'no_username'})\n"
                                      f"Reason: {abuse_result['reason']} (Confidence: {abuse_result['confidence']:.2f})")
                    self.storage.save_event("abuse_delete", {
                        "chat_id": chat_id,
                        "user_id": user_id,
                        "text": text,
                        "reason": abuse_result['reason'],
                        "confidence": abuse_result['confidence']
                    })
                    return
                except Exception as e:
                    logger.error(f"Failed to delete abusive message: {e}")
                    await self.send_log(context, f"❌ Failed to delete abusive message: {e}", 
                                      f"User: {user.full_name} (@{user.username or 'no_username'})")
        
        # Store message for edit monitoring
        # Auto delete media/sticker with configured delays
        if self.is_sticker_message(message):
            s_delay = self.get_chat_delay(chat_id, "sticker")
            if s_delay is not None and s_delay > 0:
                await self.schedule_delete_task(context, chat_id, message.message_id, s_delay)
                await self.send_log(context, f"🗓️ Sticker scheduled for deletion in {s_delay}s",
                                  f"Chat: {message.chat.title or chat_id}\nUser: {user.full_name}")
                return
        if self.is_media_message(message):
            m_delay = self.get_chat_delay(chat_id, "media")
            if m_delay is not None and m_delay > 0:
                await self.schedule_delete_task(context, chat_id, message.message_id, m_delay)
                await self.send_log(context, f"🗓️ Media scheduled for deletion in {m_delay}s",
                                  f"Chat: {message.chat.title or chat_id}\nUser: {user.full_name}")
                return
        self.edited_messages.setdefault(chat_id, {})[message.message_id] = datetime.now()
    
    async def cancel_deletion_task(self, chat_id: int, message_id: int):
        key = (chat_id, message_id)
        task = self.delete_tasks.get(key)
        if task and not task.done():
            task.cancel()
        self.delete_tasks.pop(key, None)

    async def schedule_delete_task(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int):
        await self.cancel_deletion_task(chat_id, message_id)
        import asyncio as _asyncio
        task = _asyncio.create_task(self._delayed_delete(context, chat_id, message_id, delay))
        self.delete_tasks[(chat_id, message_id)] = task

    async def _delayed_delete(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int):
        try:
            await asyncio.sleep(delay)
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            await self.send_log(context, f"⏰ Scheduled message auto-deleted", f"Chat ID: {chat_id}")
        except Exception as e:
            logger.error(f"Failed to delete scheduled message: {e}")
            await self.send_log(context, f"❌ Failed to delete scheduled message: {e}", f"Chat ID: {chat_id}")

    async def handle_edited_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle edited messages - delete after 10 seconds"""
        message = update.edited_message
        if not message:
            return

        chat_id = message.chat.id
        message_id = message.message_id
        user = message.from_user
        text = message.text or message.caption or ""
        self.storage.save_event("seen_edited", {"chat_id": chat_id, "user_id": user.id})
 
        await self.cancel_deletion_task(chat_id, message_id)

        if text and self.contains_blocked(text):
            try:
                await message.delete()
                await self.send_log(context, f"🚫 Blocklist word deleted (edited)", 
                                  f"User: {user.full_name} (@{user.username or 'no_username'})")
                return
            except Exception as e:
                logger.error(f"Failed to delete edited blocklist message: {e}")
                pass

        if self.message_has_link(message):
            try:
                await message.delete()
                reason = self.bio_detector.get_link_reason(message) or "unknown"
                await self.send_log(context, f"🗑️ Edited message link deleted", 
                                  f"User: {user.full_name} (@{user.username or 'no_username'})\nReason: {reason}")
                return
            except Exception as e:
                logger.error(f"Failed to delete edited link message: {e}")
                pass

        # 2. Abuse detection
        if ABUSE_DETECTION_ENABLED:
            abuse_result = await self.abuse_detector.detect_abuse(text)
            if abuse_result["is_abusive"] and abuse_result["confidence"] >= ABUSE_THRESHOLD:
                try:
                    await message.delete()
                    await self.send_log(context, f"🚫 Abusive edited content deleted", 
                                      f"User: {user.full_name} (@{user.username or 'no_username'})\n"
                                      f"Reason: {abuse_result['reason']} (Confidence: {abuse_result['confidence']:.2f})")
                    return
                except Exception as e:
                    logger.error(f"Failed to delete abusive edited message: {e}")
                    pass
        
        await self.schedule_delete_task(context, chat_id, message_id, EDIT_DELETE_DELAY)
        await self.send_log(context, f"✏️ Message edited - scheduled for deletion in 10s",
                          f"Chat: {message.chat.title or chat_id}\nUser: {user.full_name}")
    
    async def handle_my_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        data = update.my_chat_member
        try:
            status = data.new_chat_member.status if data and data.new_chat_member else None
        except Exception:
            status = None
        if status in ("member", "administrator"):
            self.storage.add_group(chat.id, chat.title or "")
    
    def _load_persistent_state(self):
        try:
            state = self.storage.load_state()
            if isinstance(state.get("blocklist"), list):
                self.blocklist = set(state.get("blocklist"))
            if isinstance(state.get("special_users"), list):
                self.special_users.update(state.get("special_users"))
            if isinstance(state.get("link_whitelist"), list):
                self.link_whitelist = set(state.get("link_whitelist"))
            if isinstance(state.get("media_delete_delay"), int):
                self.media_delete_delay = state.get("media_delete_delay")
            if isinstance(state.get("sticker_delete_delay"), int):
                self.sticker_delete_delay = state.get("sticker_delete_delay")
            chat_delays = state.get("chat_delays") or {}
            if isinstance(chat_delays, dict):
                self.chat_delays = chat_delays
        except Exception:
            pass

    def persist_blocklist(self):
        try:
            self.storage.update_state({"blocklist": sorted(list(self.blocklist))})
        except Exception:
            pass

    def persist_special_users(self):
        try:
            self.storage.update_state({"special_users": sorted(list(self.special_users))})
        except Exception:
            pass
    
    def persist_whitelist(self):
        try:
            self.storage.update_state({"link_whitelist": sorted(list(self.link_whitelist))})
        except Exception:
            pass

    def persist_delays(self):
        try:
            self.storage.update_state({
                "media_delete_delay": self.media_delete_delay,
                "sticker_delete_delay": self.sticker_delete_delay
            })
        except Exception:
            pass
    
    def get_chat_delay(self, chat_id: int, target: str) -> int | None:
        per = self.chat_delays.get(str(chat_id)) or self.chat_delays.get(chat_id) or {}
        if target in per:
            val = per.get(target)
            if val is None:
                return None
            if isinstance(val, int) and val >= 0:
                return val
        default = self.media_delete_delay if target == "media" else self.sticker_delete_delay
        return default
    
    def set_chat_delay(self, chat_id: int, target: str, seconds: int | None):
        entry = self.chat_delays.get(str(chat_id)) or self.chat_delays.get(chat_id) or {}
        if seconds is None or seconds <= 0:
            entry[target] = None
        else:
            entry[target] = int(seconds)
        # store using string key for consistency
        self.chat_delays[str(chat_id)] = entry
        try:
            self.storage.update_state({"chat_delays": self.chat_delays})
        except Exception:
            pass
    
    def is_whitelisted(self, message) -> bool:
        base = self.bio_detector.normalize(message.text or message.caption or "").lower()
        terms = [w.lower() for w in self.link_whitelist if w and '.' in w]
        if not terms:
            return False
        ents = []
        if getattr(message, "entities", None):
            ents += message.entities
        if getattr(message, "caption_entities", None):
            ents += message.caption_entities
        for e in ents:
            if e.type == "text_link" and getattr(e, "url", None):
                url = e.url.lower()
                for w in terms:
                    if w in url:
                        return True
            elif e.type == "url":
                seg = base[e.offset:e.offset + e.length].lower()
                for w in terms:
                    if w in seg:
                        return True
        return False
    async def is_owner_or_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        user_id = update.effective_user.id
        if user_id == OWNER_ID:
            return True
        try:
            cm = await context.bot.get_chat_member(update.effective_chat.id, user_id)
            return cm.status in ("administrator", "creator")
        except:
            return False
    
    def contains_blocked(self, text: str) -> bool:
        base = (text or "").lower()
        for w in self.blocklist:
            if w and w.lower() in base:
                return True
        return False
    
    async def delete_scheduled_message(self, context: ContextTypes.DEFAULT_TYPE):
        pass
    
    def is_media_message(self, message) -> bool:
        return any([
            bool(getattr(message, "photo", None)),
            bool(getattr(message, "video", None)),
            bool(getattr(message, "animation", None)),
            bool(getattr(message, "document", None)),
            bool(getattr(message, "audio", None)),
            bool(getattr(message, "voice", None)),
            bool(getattr(message, "video_note", None)),
        ])
    
    def is_sticker_message(self, message) -> bool:
        return bool(getattr(message, "sticker", None))
    
    def set_mongo_uri(self, uri: str) -> bool:
        try:
            import os
            os.environ["MONGO_URI"] = uri
            from storage import Storage
            self.storage = Storage(uri)
            if self.storage.enabled:
                return True
            return False
        except Exception:
            return False
    
    async def set_gpt_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set GPT API key - Owner only"""
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /setgptkey <your_gpt_api_key>")
            return
        
        new_key = " ".join(context.args)
        # Here you would save to .env or database
        # For demo, we'll set it directly
        import os
        os.environ["GPT_API_KEY"] = new_key
        self.abuse_detector.is_ready = True
        
        await update.message.reply_text("✅ GPT API key updated!")
        await self.send_log(context, "🔑 GPT API key updated by owner")
    
    async def add_special_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add special privileged user - Owner/Admin only"""
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /addspecial <user_id>")
            return
        
        try:
            user_id = int(context.args[0])
            self.special_users.add(user_id)
            await update.message.reply_text(f"✅ User {user_id} added to special privileges")
            await self.send_log(context, f"👑 Special privilege granted to user {user_id}")
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID")
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bot status command"""
        groups = self.storage.count_groups() if self.storage.enabled else 0
        users = self.storage.count_distinct_users() if self.storage.enabled else 0
        status_text = f"""
🤖 **Bot Status**
• Bot: ✅ Online
• Storage: {'✅' if self.storage.enabled else '❌'}
• Groups: {groups}
• Users: {users}
        """
        await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)
        await self.send_log(context, "📊 Status command used", f"User: {update.effective_user.full_name}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        chat_type = update.effective_chat.type
        abuse_ready = '✅' if ABUSE_DETECTION_ENABLED and self.abuse_detector.is_ready else '❌'
        updates_url = "https://t.me/acenfts"
        text = f"""
✨ **Welcome!** ✨
— — — — — — — — —
🔗 • Link detection and deletion
🤖 • AI abuse detection: {abuse_ready}
⏱️ • Auto-delete edited messages after 10 seconds
📘 • Try /help for commands and usage
— — — — — — — — —
"""
        owner_url = "tg://user?id=6669036797"
        buttons = [
            InlineKeyboardButton("🆘 Help", callback_data="HELP"),
            InlineKeyboardButton("🆕 Updates", url=updates_url) if updates_url else InlineKeyboardButton("🆕 Updates", callback_data="UPDATES"),
            InlineKeyboardButton("👑 Owner", url=owner_url)
        ]
        reply_markup = InlineKeyboardMarkup([buttons])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        await self.send_log(context, "🚀 Start command used", f"User: {update.effective_user.full_name}")
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = f"""
� **Help**
• /start — welcome and features
• /status — bot status
• /setgptkey <key> — owner only
• /addspecial <user_id> — owner only
Bot auto-removes links and abusive content. Edited messages are removed after 10 seconds.
        """
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        await self.send_log(context, "❓ Help command used", f"User: {update.effective_user.full_name}")
    
    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        data = q.data if q and q.data else ""
        try:
            await q.answer()
        except Exception:
            pass
        if data == "HELP":
            text = (
                "📖 <b>Help</b>\n"
                "• <code>/start</code> — welcome and features\n"
                "• <code>/status</code> — bot status\n"
                "• <code>/setgptkey &lt;key&gt;</code> — owner only\n"
                "• <code>/addspecial &lt;user_id&gt;</code> — owner only\n"
                "• <code>/free</code> — owner/admin: exempt a user (reply or id)\n"
                "• <code>/approve</code> — owner/admin: cancel deletion for replied message\n"
                "• <code>/blockadd &lt;word or phrase&gt;</code> — owner only\n"
                "• <code>/blocklist</code> — owner only\n"
                "• <code>/setdelay &lt;media|sticker&gt; &lt;seconds|1s|1m&gt;</code>\n"
            )
            await q.message.reply_text(text, parse_mode=ParseMode.HTML)
            await self.send_log(context, "🆘 Inline Help used", f"User: {update.effective_user.full_name}")
            return
        if data == "UPDATES":
            info = f"📢 Updates group/channel: {SUPPORT_GROUP_ID}"
            await q.message.reply_text(info)
            await self.send_log(context, "🆕 Inline Updates used", f"User: {update.effective_user.full_name}")
            return
        if data == "OWNER":
            owner_link = f'<a href="tg://user?id=6669036797">Contact Owner</a>'
            await q.message.reply_text(f"👑 {owner_link}", parse_mode=ParseMode.HTML)
            await self.send_log(context, "👑 Inline Owner used", f"User: {update.effective_user.full_name}")
            return
    
    def run(self):
        """Start the bot"""
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Handlers
        application.add_handler(MessageHandler(filters.UpdateType.MESSAGE & ((filters.TEXT & ~filters.COMMAND) | (filters.CAPTION & ~filters.COMMAND)), self.handle_message))
        application.add_handler(MessageHandler(
            filters.UpdateType.MESSAGE & ~filters.COMMAND & ~filters.TEXT & ~filters.CAPTION,
            self.handle_message
        ))
        application.add_handler(MessageHandler(
            (filters.UpdateType.EDITED_MESSAGE) & ((filters.TEXT) | (filters.CAPTION)),
            self.handle_edited_message
        ))
        application.add_handler(CallbackQueryHandler(self.handle_button))
        application.add_handler(ChatMemberHandler(self.handle_my_chat_member))
        
        # Commands
        application.add_handler(CommandHandler("setgptkey", self.set_gpt_key))
        application.add_handler(CommandHandler("addspecial", self.add_special_user))
        application.add_handler(CommandHandler("status", self.status))
        application.add_handler(CommandHandler("start", self.start))
        register_help_commands(application, self)
        
        # Error handler
        application.add_error_handler(self.error_handler)
        
        print("🚀 Bot started!")
        application.run_polling()

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Update {update} caused error {context.error}")
        
        # Don't spam logs for conflict errors (multiple instances)
        if isinstance(context.error, Conflict):
            print("❌ Conflict Error: Another instance is running. Shutting down polling to avoid spam.")
            return

        # Don't spam logs for network errors
        if isinstance(context.error, NetworkError):
            print(f"⚠️ Network Error: {context.error}")
            return
            
        await self.send_log(context, f"❌ Bot Error: {context.error}")
        
if __name__ == "__main__":
    bot = BioLinkBot()
    bot.run()
