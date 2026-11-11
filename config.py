"""
Configuration module for the Flight Price Monitoring Automation.
Loads settings from .env file or environment variables with safe defaults.
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent

def load_dotenv(dotenv_path: Optional[Path] = None):
    """Simple, reliable .env parser with zero external dependencies."""
    if dotenv_path is None:
        dotenv_path = BASE_DIR / ".env"
    if not dotenv_path.exists():
        return
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = val

load_dotenv()

@dataclass
class Settings:
    # Route parameters
    origin: str = os.getenv("ORIGIN_AIRPORT", "CGK")
    destination: str = os.getenv("DESTINATION_AIRPORT", "CTS")
    origin_name: str = os.getenv("ROUTE_ORIGIN_NAME", "Jakarta (CGK)")
    dest_name: str = os.getenv("ROUTE_DEST_NAME", "Sapporo (CTS)")
    travel_year: int = int(os.getenv("TRAVEL_YEAR", "2027"))
    travel_month: int = int(os.getenv("TRAVEL_MONTH", "11"))
    passengers: int = int(os.getenv("PASSENGERS", "1"))
    cabin_class: str = os.getenv("CABIN_CLASS", "ECONOMY")

    # Budget & thresholds
    target_budget_idr: float = float(os.getenv("TARGET_BUDGET_IDR", "7500000"))
    price_drop_threshold: float = float(os.getenv("PRICE_DROP_THRESHOLD", "0.05"))
    timezone: str = os.getenv("TIMEZONE", "Asia/Jakarta")

    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Optional APIs
    amadeus_client_id: str = os.getenv("AMADEUS_CLIENT_ID", "")
    amadeus_client_secret: str = os.getenv("AMADEUS_CLIENT_SECRET", "")
    serpapi_key: str = os.getenv("SERPAPI_API_KEY", "")

    # Database
    db_path: Path = BASE_DIR / "flight_tracker.db"

settings = Settings()

class SensitiveFilter(logging.Filter):
    """Filter that masks sensitive tokens from logging output."""
    def filter(self, record):
        if hasattr(record, "msg") and isinstance(record.msg, str):
            if settings.telegram_bot_token and len(settings.telegram_bot_token) > 10:
                record.msg = record.msg.replace(settings.telegram_bot_token, "[REDACTED_BOT_TOKEN]")
        return True

def setup_logger(name: str = "flight_tracker") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        ch.addFilter(SensitiveFilter())
        logger.addHandler(ch)

        # File handler
        log_file = BASE_DIR / "flight_tracker.log"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        fh.addFilter(SensitiveFilter())
        logger.addHandler(fh)

    return logger

logger = setup_logger()
