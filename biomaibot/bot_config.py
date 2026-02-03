import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env explicitly
env_path = Path(__file__).parent / '.env'
loaded = load_dotenv(dotenv_path=env_path)

if not loaded:
    print(f"Warning: .env file not loaded from {env_path} via load_dotenv. Trying manual parsing.")
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value
                    print(f"Loaded {key} manually.")
    except Exception as e:
        print(f"Manual .env parsing failed: {e}")

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")

owner_id_str = os.getenv("OWNER_ID")
if not owner_id_str or not owner_id_str.isdigit():
    print(f"Warning: Invalid OWNER_ID in .env: {owner_id_str}. Using 0.")
    OWNER_ID = 0
else:
    OWNER_ID = int(owner_id_str)

support_group_str = os.getenv("SUPPORT_GROUP_ID", "-1001234567890")
try:
    SUPPORT_GROUP_ID = int(support_group_str)
except ValueError:
    print(f"Warning: Invalid SUPPORT_GROUP_ID: {support_group_str}. Using 0.")
    SUPPORT_GROUP_ID = 0

GPT_API_KEY = os.getenv("GPT_API_KEY")

# Special privileges users (comma separated)
special_users_str = os.getenv("SPECIAL_USERS", "")
SPECIAL_USERS = [int(x.strip()) for x in special_users_str.split(",") if x.strip().isdigit()]

# Log channel/group ID
log_channel_str = os.getenv("LOG_CHANNEL_ID", "-1001234567890")
try:
    LOG_CHANNEL_ID = int(log_channel_str)
except ValueError:
    print(f"Warning: Invalid LOG_CHANNEL_ID: {log_channel_str}. Using 0.")
    LOG_CHANNEL_ID = 0

# Abuse detection settings
ABUSE_DETECTION_ENABLED = os.getenv("ABUSE_DETECTION_ENABLED", "true").lower() == "true"
abuse_threshold_str = os.getenv("ABUSE_THRESHOLD", "0.8")
try:
    ABUSE_THRESHOLD = float(abuse_threshold_str)
except ValueError:
    ABUSE_THRESHOLD = 0.8

# Time settings
EDIT_DELETE_DELAY = 10  # 10 seconds
MEDIA_DELETE_DELAY = int(os.getenv("MEDIA_DELETE_DELAY", "30"))  # default 30s
STICKER_DELETE_DELAY = int(os.getenv("STICKER_DELETE_DELAY", "30"))  # default 30s

# MongoDB and moderation config
MONGO_URI = os.getenv("MONGO_URI", "")
DEFAULT_WARNING_LIMIT = int(os.getenv("DEFAULT_WARNING_LIMIT", "3"))
DEFAULT_PUNISHMENT = os.getenv("DEFAULT_PUNISHMENT", "mute")
DEFAULT_CONFIG = ("warn", DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT)
