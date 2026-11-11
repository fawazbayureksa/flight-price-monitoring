"""
Dashboard & Monitoring module for Flight Price Monitoring.
Displays current tracking metrics, lowest fares, budget status, horizon state, and alert logs.
"""

from typing import Dict, Any
from datetime import datetime
from config import settings
from database import db
from flight_search import flight_service

def render_dashboard() -> str:
    """Generates a comprehensive terminal dashboard string."""
    summary = db.get_dashboard_summary()
    date_pairs = flight_service.get_sample_date_pairs()
    horizon = flight_service.check_booking_horizon(date_pairs[0]["departure"])

    lines = []
    lines.append("=" * 78)
    lines.append("       ✈️  FLIGHT PRICE MONITORING DASHBOARD: JAKARTA (CGK) -> SAPPORO (CTS)       ")
    lines.append("=" * 78)
    lines.append(f"• Monitored Route    : {settings.origin_name} to {settings.dest_name}")
    lines.append(f"• Travel Window      : November 1–30, {settings.travel_year}")
    lines.append(f"• Target Budget      : IDR {int(settings.target_budget_idr):,}".replace(",", "."))
    lines.append(f"• GDS Horizon Status : {horizon['gds_horizon_status']}")
    lines.append(f"• LCC Horizon Status : {horizon['lcc_horizon_status']}")
    lines.append(f"• Schedule Cadence   : Daily at 09:00 WIB (Asia/Jakarta)")
    lines.append("-" * 78)

    # Search Execution Stats
    last_run = summary["last_run"]
    if last_run:
        lines.append(f"Last Search Run      : {last_run['run_timestamp']} | Status: {last_run['status']}")
        lines.append(f"Total Search Runs    : {summary['total_runs']} | Total Alerts Sent: {summary['total_alerts']}")
    else:
        lines.append("Last Search Run      : No search runs recorded yet. (Run with --run-once)")

    lines.append("-" * 78)

    # Lowest Price Status
    lowest = summary["lowest_offer"]
    if lowest:
        p = lowest["price_idr"]
        b = settings.target_budget_idr
        diff = b - p
        status = "WITHIN BUDGET (SAVINGS)" if diff >= 0 else "EXCEEDS BUDGET"
        lines.append(f"🌟 CURRENT LOWEST FARE FOUND:")
        lines.append(f"   Airline      : {lowest['airline']} ({lowest.get('flight_number', 'N/A')})")
        lines.append(f"   Dates        : {lowest['departure_date']} to {lowest['return_date']}")
        lines.append(f"   Price        : IDR {int(p):,}".replace(",", "."))
        lines.append(f"   Budget Delta : IDR {int(abs(diff)):,}".replace(",", ".") + f" [{status}]")
        lines.append(f"   Duration     : {lowest['total_duration']} | Transit: {lowest['transit_info']}")
        lines.append(f"   Baggage      : Cabin: {lowest['cabin_baggage']} | Checked: {lowest['checked_baggage']}")
        lines.append(f"   Booking Link : {lowest['booking_url']}")
    else:
        lines.append("🌟 CURRENT LOWEST FARE FOUND: Awaiting flight search data.")

    lines.append("-" * 78)

    # Notification History
    lines.append("🔔 RECENT NOTIFICATIONS SENT:")
    alerts = summary["recent_alerts"]
    if alerts:
        for a in alerts:
            p_str = f"IDR {int(a['price_idr']):,}".replace(",", ".")
            lines.append(f"   [{a['sent_at'][:19]}] {a['alert_type']:<18} | {a['airline']:<15} | {a['departure_date']} | {p_str}")
    else:
        lines.append("   No notifications dispatched yet.")

    lines.append("-" * 78)

    # Price History & Trends
    lines.append("📈 RECENT PRICE HISTORY & TRENDS:")
    prices = summary["recent_prices"]
    if prices:
        lines.append(f"   {'Date Recorded':<19} | {'Airline':<16} | {'Dates':<23} | {'Price (IDR)':<14}")
        lines.append(f"   {'-'*19}-+-{'-'*16}-+-{'-'*23}-+-{'-'*14}")
        for ph in prices:
            p_str = f"IDR {int(ph['price_idr']):,}".replace(",", ".")
            d_str = f"{ph['departure_date']}..{ph['return_date']}"
            lines.append(f"   {ph['recorded_at'][:19]:<19} | {ph['airline']:<16} | {d_str:<23} | {p_str:<14}")
    else:
        lines.append("   No historical price points recorded yet.")

    lines.append("-" * 78)

    # Real-time search verification links
    lines.append("🔗 DIRECT SEARCH / BOOKING VERIFICATION LINKS:")
    for pair in date_pairs[:3]:
        lines.append(f"   • {pair['desc']}:")
        lines.append(f"     Google Flights: {flight_service.build_google_flights_url(pair['departure'], pair['return'])}")
        lines.append(f"     Skyscanner    : {flight_service.build_skyscanner_url(pair['departure'], pair['return'])}")

    lines.append("=" * 78)
    return "\n".join(lines)

def print_dashboard():
    print(render_dashboard())
