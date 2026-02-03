from telegram.constants import ParseMode
from telegram.ext import CommandHandler
from bot_config import OWNER_ID, SUPPORT_GROUP_ID

def register_help_commands(application, bot):
    application.add_handler(CommandHandler("help", make_help(bot)))
    application.add_handler(CommandHandler("free", make_free(bot)))
    application.add_handler(CommandHandler("approve", make_approve(bot)))
    application.add_handler(CommandHandler("blockadd", make_blockadd(bot)))
    application.add_handler(CommandHandler("blocklist", make_blocklist(bot)))
    application.add_handler(CommandHandler("setdelay", make_setdelay(bot)))
    application.add_handler(CommandHandler("setmongo", make_setmongo(bot)))
    application.add_handler(CommandHandler("linkapprove", make_linkapprove(bot)))
    application.add_handler(CommandHandler("linkwhitelist", make_linkwhitelist(bot)))

def make_help(bot):
    async def handler(update, context):
        import html
        text = (
            "📖 <b>Help</b>\n"
            f"• <code>/start</code> — welcome and features\n"
            f"• <code>/status</code> — bot status\n"
            f"• <code>/setgptkey &lt;key&gt;</code> — owner only\n"
            f"• <code>/addspecial &lt;user_id&gt;</code> — owner only\n"
            f"• <code>/free</code> — owner/admin: exempt a user (reply or id)\n"
            f"• <code>/approve</code> — owner/admin: cancel deletion for replied message\n"
            f"• <code>/blockadd &lt;word or phrase&gt;</code> — owner only: add to blocklist\n"
            f"• <code>/blocklist</code> — owner only: show all blocked words\n"
            f"• <code>/setdelay &lt;media|sticker&gt; &lt;seconds|1s|1m|off&gt;</code> — per-group auto-delete\n"
            "Bot auto-removes links and abusive content. Edited messages are removed after 10 seconds."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        await bot.send_log(context, "❓ Help command used", f"User: {update.effective_user.full_name}")
    return handler

def make_free(bot):
    async def handler(update, context):
        if not await bot.is_owner_or_admin(update, context):
            await update.message.reply_text("❌ Unauthorized")
            return
        target_id = None
        if update.message.reply_to_message:
            target_id = update.message.reply_to_message.from_user.id
        elif context.args:
            try:
                target_id = int(context.args[0])
            except:
                target_id = None
        if not target_id:
            await update.message.reply_text("Usage: /free <user_id> or reply to a user")
            return
        bot.special_users.add(target_id)
        await update.message.reply_text(f"✅ User {target_id} set to free")
        await bot.send_log(context, f"🆓 User set free {target_id}")
        bot.persist_special_users()
    return handler

def make_setdelay(bot):
    async def handler(update, context):
        if not await bot.is_owner_or_admin(update, context):
            await update.message.reply_text("❌ Unauthorized")
            return
        if len(context.args) != 2 or context.args[0].lower() not in ("media", "sticker"):
            await update.message.reply_text("Usage: /setdelay <media|sticker> <seconds|1s|1m|off>")
            return
        target = context.args[0].lower()
        raw = context.args[1].strip().lower()
        seconds = None
        if raw == "off":
            seconds = None
        elif raw.endswith(("sec", "s")):
            num = raw.rstrip("sec").rstrip("s")
            if num.isdigit():
                seconds = int(num)
        elif raw.endswith(("min", "m")):
            num = raw.rstrip("min").rstrip("m")
            if num.isdigit():
                seconds = int(num) * 60
        elif raw.isdigit():
            seconds = int(raw)
        else:
            await update.message.reply_text("❌ Invalid time. Use seconds, 1s/1m, or off")
            return
        if seconds is not None:
            seconds = max(1, min(3600, seconds))
        chat_id = update.effective_chat.id
        bot.set_chat_delay(chat_id, target, seconds)
        if seconds is None:
            await update.message.reply_text(f"✅ {target.capitalize()} auto-delete turned OFF for this group")
            await bot.send_log(context, f"⏱️ Turned OFF {target} auto-delete", f"Chat: {update.effective_chat.title or chat_id}")
        else:
            await update.message.reply_text(f"✅ {target.capitalize()} auto-delete delay set to {seconds}s for this group")
            await bot.send_log(context, f"⏱️ Set {target} delete delay to {seconds}s", f"Chat: {update.effective_chat.title or chat_id}")
        # global delays persist left as-is; per-chat delays are persisted via bot.set_chat_delay
    return handler

def make_setmongo(bot):
    async def handler(update, context):
        if not await bot.is_owner_or_admin(update, context):
            await update.message.reply_text("❌ Unauthorized")
            return
        if not context.args:
            await update.message.reply_text("Usage: /setmongo <mongodb_uri>")
            return
        uri = " ".join(context.args).strip()
        ok = bot.set_mongo_uri(uri)
        if ok:
            await update.message.reply_text("✅ MongoDB connected")
            await bot.send_log(context, "🗄️ MongoDB connected via command", f"By: {update.effective_user.full_name}")
        else:
            await update.message.reply_text("❌ MongoDB connection failed")
    return handler

def make_approve(bot):
    async def handler(update, context):
        if not await bot.is_owner_or_admin(update, context):
            await update.message.reply_text("❌ Unauthorized")
            return
        if not update.message.reply_to_message:
            await update.message.reply_text("Usage: Reply to a message and send /approve")
            return
        chat_id = update.message.chat.id
        message_id = update.message.reply_to_message.message_id
        await bot.cancel_deletion_task(chat_id, message_id)
        await update.message.reply_text("✅ Approved. Auto-delete canceled.")
        await bot.send_log(context, "✅ Approved message; deletion canceled", f"Chat: {update.effective_chat.title or chat_id}")
    return handler

def make_blockadd(bot):
    async def handler(update, context):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("yash papa se milo")
            return
        phrase = None
        if context.args:
            phrase = " ".join(context.args).strip()
        elif update.message and update.message.reply_to_message:
            phrase = (update.message.reply_to_message.text or update.message.reply_to_message.caption or "").strip()
        if not phrase:
            await update.message.reply_text("Usage: /blockadd <word or phrase> or reply to a message")
            return
        bot.blocklist.add(phrase)
        await update.message.reply_text(f"✅ Added to blocklist: {phrase}")
        await bot.send_log(context, f"🛑 Blocklist added: {phrase}", f"By: {update.effective_user.full_name}")
        bot.persist_blocklist()
        if update.message and update.message.reply_to_message:
            try:
                await update.message.reply_to_message.delete()
                await bot.send_log(context, "🗑️ Deleted replied message after blockadd", f"Chat: {update.effective_chat.title or update.effective_chat.id}")
            except:
                pass
    return handler

def make_blocklist(bot):
    async def handler(update, context):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("yash papa se milo")
            return
        if not bot.blocklist:
            await update.message.reply_text("ℹ️ Blocklist empty")
            return
        words = "\n".join(sorted(bot.blocklist))
        text = f"🛑 Blocklist words:\n{words}"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return handler

def make_linkapprove(bot):
    async def handler(update, context):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("yash papa se milo")
            return
        if not context.args:
            await update.message.reply_text("Usage: /linkapprove <domain or substring>")
            return
        phrase = " ".join(context.args).strip().lower()
        if not phrase:
            await update.message.reply_text("❌ Invalid input")
            return
        bot.link_whitelist.add(phrase)
        bot.persist_whitelist()
        await update.message.reply_text(f"✅ Approved link: {phrase}")
        await bot.send_log(context, f"✅ Link approved: {phrase}", f"By: {update.effective_user.full_name}")
    return handler

def make_linkwhitelist(bot):
    async def handler(update, context):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("yash papa se milo")
            return
        if not bot.link_whitelist:
            await update.message.reply_text("ℹ️ Link whitelist empty")
            return
        words = "\n".join(sorted(bot.link_whitelist))
        text = f"✅ Approved links:\n{words}"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return handler
