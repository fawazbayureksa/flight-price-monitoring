"""
Price Analysis module for Flight Price Monitoring.
Evaluates discovered flight offers against target thresholds:
1. Within budget (<= IDR 7,500,000)
2. New lowest recorded price
3. Significant price drop (>= 5% decrease from previously recorded fare)
Prevents duplicate alert dispatches.
"""

from typing import Dict, Any, List, Tuple, Optional
from config import settings, logger
from database import db

class PriceAnalyzer:
    def __init__(self):
        self.budget = settings.target_budget_idr
        self.drop_threshold = settings.price_drop_threshold

    def evaluate_offer(self, offer: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Evaluates a single flight offer.
        Returns: (should_alert, alert_type, reason_description)
        """
        price = float(offer.get("price_idr", 0))
        airline = offer.get("airline", "Unknown")
        dep_date = offer.get("departure_date", "")
        ret_date = offer.get("return_date", "")

        if price <= 0:
            return False, None, None

        # Check all-time lowest price in DB before recording this offer
        lowest_record = db.get_all_time_lowest_price(settings.travel_year)
        prev_price = db.get_previous_price(airline, dep_date, ret_date)

        alert_type = None
        reason = ""

        # Condition 3: New lowest recorded price overall
        if lowest_record is not None and price < lowest_record["price_idr"]:
            alert_type = "NEW LOWEST PRICE"
            diff = lowest_record["price_idr"] - price
            pct = (diff / lowest_record["price_idr"]) * 100
            reason = f"New lowest price overall: IDR {price:,.0f} (beats previous low of IDR {lowest_record['price_idr']:,.0f} by {pct:.1f}%)"

        # Condition 2: Significant price decrease (>= 5%) from previous record for same route/dates
        elif prev_price is not None and prev_price > 0:
            price_drop = prev_price - price
            drop_pct = price_drop / prev_price
            if drop_pct >= self.drop_threshold:
                alert_type = "PRICE DROP"
                reason = f"Price dropped {drop_pct*100:.1f}% from previous record (was IDR {prev_price:,.0f}, now IDR {price:,.0f})"

        # Condition 1: Within target budget (<= IDR 7,500,000)
        elif price <= self.budget:
            alert_type = "WITHIN BUDGET"
            savings = self.budget - price
            reason = f"Price is within budget: IDR {price:,.0f} (savings of IDR {savings:,.0f})"

        if not alert_type:
            return False, None, None

        # Check deduplication
        if db.is_duplicate_alert(airline, dep_date, ret_date, price, alert_type):
            logger.info(f"Duplicate alert skipped for {airline} ({dep_date} to {ret_date}) at IDR {price:,.0f} [{alert_type}]")
            return False, None, None

        return True, alert_type, reason

    def analyze_batch(self, offers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyzes a list of offers and tags qualifying offers with their alert types.
        """
        qualifying = []
        for offer in offers:
            should_alert, alert_type, reason = self.evaluate_offer(offer)
            if should_alert:
                qualifying.append({
                    "offer": offer,
                    "alert_type": alert_type,
                    "reason": reason
                })
        return qualifying

analyzer = PriceAnalyzer()
