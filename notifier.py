"""
Telegram notification module for Flight Price Monitoring.
Formats alerts according to user specifications and delivers them via the Telegram Bot API.
"""

import urllib.request
import urllib.parse
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
import zoneinfo

from config import settings, logger

class TelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        try:
            self.tz = zoneinfo.ZoneInfo(settings.timezone)
        except Exception:
            self.tz = None

    def get_current_time_wib_str(self) -> str:
        """Returns the current date and time formatted in WIB."""
        now = datetime.now(self.tz) if self.tz else datetime.now()
        return now.strftime("%d %B %Y, %H:%M WIB")

    def format_price(self, price: float) -> str:
        """Formats a float price into standard Indonesian Rupiah format (e.g. 6.850.000)."""
        return f"{int(round(price)):,}".replace(",", ".")

    def build_alert_message(self, offer: Dict[str, Any], indicator: str) -> str:
        """
        Builds the flight alert message strictly following the requested format:

        ✈️ FLIGHT PRICE ALERT

        Route: Jakarta (CGK) → Sapporo (CTS)
        Travel Dates: [Departure Date] – [Return Date]
        Airline: [Airline Name]
        Flight Duration: [Total Duration]
        Transit: [Transit Airport / Direct]

        💰 Price: IDR [Price]
        Budget: IDR 7,500,000
        Savings: IDR [Difference from Budget]

        Baggage:
        - Cabin: [Allowance]
        - Checked: [Allowance]

        Booking Source: [Provider]
        Booking URL: [Direct Search / Booking URL]

        Price Checked: [Date and Time in WIB]

        [WITHIN BUDGET / NEW LOWEST PRICE / PRICE DROP]
        """
        price = float(offer.get("price_idr", 0))
        budget = settings.target_budget_idr
        diff = budget - price
        
        if diff >= 0:
            savings_str = f"IDR {self.format_price(diff)} (Below Budget)"
        else:
            savings_str = f"-IDR {self.format_price(abs(diff))} (Exceeds Budget)"

        formatted_price = self.format_price(price)
        formatted_budget = self.format_price(budget)
        time_checked = self.get_current_time_wib_str()

        # Format indicator tag nicely
        clean_indicator = indicator.strip()
        if not (clean_indicator.startswith("[") and clean_indicator.endswith("]")):
            indicator_badge = f"[{clean_indicator}]"
        else:
            indicator_badge = clean_indicator

        msg = (
            "✈️ FLIGHT PRICE ALERT\n\n"
            f"Route: {settings.origin_name} → {settings.dest_name}\n"
            f"Travel Dates: {offer.get('departure_date', 'N/A')} – {offer.get('return_date', 'N/A')}\n"
            f"Airline: {offer.get('airline', 'N/A')}\n"
            f"Flight Duration: {offer.get('total_duration', 'N/A')}\n"
            f"Transit: {offer.get('transit_info', 'Direct')}\n\n"
            f"💰 Price: IDR {formatted_price}\n"
            f"Budget: IDR {formatted_budget}\n"
            f"Savings: {savings_str}\n\n"
            "Baggage:\n"
            f"- Cabin: {offer.get('cabin_baggage', 'Standard 7kg')}\n"
            f"- Checked: {offer.get('checked_baggage', 'Not Included / Additional fee')}\n\n"
            f"Booking Source: {offer.get('booking_source', 'Flight Aggregator')}\n"
            f"Booking URL: {offer.get('booking_url', 'N/A')}\n\n"
            f"Price Checked: {time_checked}\n\n"
            f"{indicator_badge}"
        )
        return msg

    def send_message(self, text: str, max_retries: int = 3) -> bool:
        """
        Sends a message to the configured Telegram chat with retries.
        Never logs the raw bot token in any exception or log.
        """
        if not self.bot_token or not self.chat_id:
            logger.error("Telegram bot token or chat ID is missing in configuration.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": "false"
        }).encode("utf-8")

        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    if resp_data.get("ok"):
                        logger.info("Telegram notification delivered successfully.")
                        return True
                    else:
                        logger.warning(f"Telegram returned not ok: {resp_data}")
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                logger.warning(f"HTTP error {e.code} sending Telegram alert: {err_body}")
                if "chat not found" in err_body or "blocked" in err_body:
                    logger.error(
                        "ACTION REQUIRED: The user has not started a conversation with the Telegram bot yet! "
                        "Please open https://t.me/RexxTripHunterBot and click /start."
                    )
                    return False
            except Exception as e:
                logger.warning(f"Attempt {attempt}/{max_retries} failed sending Telegram alert: {e}")
            
            if attempt < max_retries:
                time.sleep(2 * attempt)

        logger.error("Failed to send Telegram message after all retries.")
        return False

notifier = TelegramNotifier()
