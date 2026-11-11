"""
Main entry point for Flight Price Monitoring Automation.
CGK (Jakarta) -> CTS (Sapporo, Japan) | November 2027

Usage:
    python main.py --run-once
    python main.py --dashboard
    python main.py --test-telegram
    python main.py --simulate-sample
    python main.py --schedule
"""

import sys
import time
import argparse
from datetime import datetime
import zoneinfo

from config import settings, logger
from database import db
from flight_search import flight_service
from price_analyzer import analyzer
from notifier import notifier
from dashboard import print_dashboard

def execute_search_cycle(use_sample_data: bool = False):
    """
    Executes a single monitoring cycle:
    1. Checks schedule horizon & queries flight providers.
    2. Evaluates discovered offers against budget and previous records.
    3. Persists records to SQLite.
    4. Sends Telegram alerts for qualifying tickets.
    """
    logger.info("=" * 60)
    logger.info(f"Starting flight search cycle: {settings.origin_name} -> {settings.dest_name} ({settings.travel_year}-11)")
    
    # 1. Fetch offers
    if use_sample_data:
        logger.info("Using baseline market route data for verification...")
        offers = flight_service.get_sample_test_offers()
        search_res = {
            "status": "SAMPLE_DATA_LOADED",
            "notes": "Loaded verified baseline market offers for pipeline verification.",
            "offers": offers
        }
    else:
        search_res = flight_service.search_all_sources()
        offers = search_res.get("offers", [])

    lowest_price = min([o["price_idr"] for o in offers]) if offers else None

    # 2. Record search run in database
    run_id = db.record_search_run(
        origin=settings.origin,
        dest=settings.destination,
        travel_month=f"{settings.travel_year}-{settings.travel_month:02d}",
        total_offers=len(offers),
        lowest_price=lowest_price,
        status=search_res.get("status", "SUCCESS"),
        notes=search_res.get("notes", "")
    )
    logger.info(f"Recorded search run #{run_id} with {len(offers)} offers. Lowest: IDR {lowest_price:,.0f}" if lowest_price else f"Recorded search run #{run_id} (0 offers returned from active APIs).")

    # 3. Analyze prices & save offers
    qualifying_alerts = []
    for offer in offers:
        offer_id = db.save_flight_offer(run_id, offer)
        offer["id"] = offer_id

        should_alert, alert_type, reason = analyzer.evaluate_offer(offer)
        if should_alert:
            qualifying_alerts.append({
                "offer": offer,
                "alert_type": alert_type,
                "reason": reason
            })

    # 4. Dispatch Telegram notifications
    if qualifying_alerts:
        logger.info(f"Found {len(qualifying_alerts)} qualifying alerts to send to Telegram.")
        for item in qualifying_alerts:
            offer = item["offer"]
            alert_type = item["alert_type"]
            msg = notifier.build_alert_message(offer, alert_type)
            
            logger.info(f"Dispatching [{alert_type}] alert for {offer['airline']} @ IDR {offer['price_idr']:,.0f}...")
            sent = notifier.send_message(msg)
            if sent:
                db.record_alert_sent(
                    offer_id=offer.get("id"),
                    alert_type=alert_type,
                    airline=offer.get("airline", "Unknown"),
                    departure_date=offer.get("departure_date", ""),
                    return_date=offer.get("return_date", ""),
                    price_idr=offer.get("price_idr", 0.0),
                    message_text=msg
                )
    else:
        logger.info("No new qualifying flight alerts triggered this run.")

    logger.info("Flight search cycle completed successfully.")
    logger.info("=" * 60)

def test_telegram_connection():
    """Sends a sample flight price alert to Telegram to verify credentials and connectivity."""
    logger.info("Verifying Telegram configuration...")
    sample_offers = flight_service.get_sample_test_offers()
    sample_offer = sample_offers[0]
    
    test_msg = notifier.build_alert_message(sample_offer, "WITHIN BUDGET")
    print("\n--- SAMPLE TELEGRAM MESSAGE PREVIEW ---")
    print(test_msg)
    print("---------------------------------------\n")
    
    logger.info("Sending test message to Telegram...")
    success = notifier.send_message(test_msg)
    if success:
        print("✅ Telegram notification successfully sent!")
    else:
        print("❌ Failed to send Telegram notification.")
        print("💡 NOTE: If error is 'chat not found', please open Telegram, search for @RexxTripHunterBot and send '/start', then re-run.")

def run_schedule_loop():
    """
    Runs an internal scheduler loop that triggers at 09:00 WIB every day.
    """
    try:
        tz = zoneinfo.ZoneInfo(settings.timezone)
    except Exception:
        tz = None

    logger.info(f"Starting schedule loop. Target execution time: 09:00 daily ({settings.timezone}).")
    last_executed_day = None

    while True:
        now = datetime.now(tz) if tz else datetime.now()
        current_day = now.date()
        
        # Check if it's 09:00 AM (between 09:00:00 and 09:00:59) and hasn't run today
        if now.hour == 9 and now.minute == 0 and last_executed_day != current_day:
            logger.info(f"Scheduled trigger activated at {now.isoformat()}. Executing daily search...")
            execute_search_cycle()
            last_executed_day = current_day

        time.sleep(30)

def main():
    parser = argparse.ArgumentParser(description="Flight Price Monitoring Automation: CGK -> CTS (Sapporo)")
    parser.add_argument("--run-once", action="store_true", help="Execute flight search and alert cycle once immediately")
    parser.add_argument("--simulate-sample", action="store_true", help="Load verified baseline market offers to test pricing and alert delivery")
    parser.add_argument("--dashboard", action="store_true", help="Display the monitoring dashboard")
    parser.add_argument("--test-telegram", action="store_true", help="Send a test notification to Telegram to verify setup")
    parser.add_argument("--schedule", action="store_true", help="Run the continuous scheduler (09:00 WIB daily)")

    args = parser.parse_args()

    if args.run_once:
        execute_search_cycle(use_sample_data=False)
        print_dashboard()
    elif args.simulate_sample:
        execute_search_cycle(use_sample_data=True)
        print_dashboard()
    elif args.dashboard:
        print_dashboard()
    elif args.test_telegram:
        test_telegram_connection()
    elif args.schedule:
        run_schedule_loop()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
