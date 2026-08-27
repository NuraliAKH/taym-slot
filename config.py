import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Default Uzum Seller settings
UZUM_BASE_API_URL = os.getenv("UZUM_BASE_API_URL", "https://api-seller.uzum.uz")
DEFAULT_POLL_INTERVAL = float(os.getenv("DEFAULT_POLL_INTERVAL", "2.0")) # seconds
DEFAULT_TIMEOUT = float(os.getenv("DEFAULT_TIMEOUT", "10.0"))

# Database path
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "uzum_bot.db"))

# Timezone (Uzbekistan is UTC+5)
TIMEZONE_OFFSET = 5 # Tashkent UTC+5

# Default browser headers to prevent blocks
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9,uz;q=0.8,en;q=0.7",
    "Content-Type": "application/json",
    "Referer": "https://seller.uzum.uz/",
    "Origin": "https://seller.uzum.uz",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
