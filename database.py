"""
SQLite Database persistence module for Flight Price Monitoring.
Tracks search executions, discovered flight offers, price history, and notification logs.
"""

import sqlite3
from typing import List, Dict, Optional, Any
from datetime import datetime
from config import settings, logger

class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or settings.db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates the necessary database tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Search execution runs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_timestamp TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    travel_month TEXT NOT NULL,
                    total_offers_found INTEGER DEFAULT 0,
                    lowest_price_found REAL,
                    status TEXT NOT NULL,
                    notes TEXT
                )
            """)

            # Discovered flight offers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS flight_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    airline TEXT NOT NULL,
                    flight_number TEXT,
                    departure_date TEXT NOT NULL,
                    return_date TEXT NOT NULL,
                    total_duration TEXT,
                    transit_info TEXT,
                    price_idr REAL NOT NULL,
                    cabin_baggage TEXT,
                    checked_baggage TEXT,
                    booking_source TEXT,
                    booking_url TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES search_runs (id)
                )
            """)

            # Price history for trends
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    airline TEXT NOT NULL,
                    departure_date TEXT NOT NULL,
                    return_date TEXT NOT NULL,
                    price_idr REAL NOT NULL,
                    recorded_at TEXT NOT NULL
                )
            """)

            # Sent Telegram alerts to prevent duplicate notifications
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts_sent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    offer_id INTEGER,
                    alert_type TEXT NOT NULL,
                    airline TEXT NOT NULL,
                    departure_date TEXT NOT NULL,
                    return_date TEXT NOT NULL,
                    price_idr REAL NOT NULL,
                    message_text TEXT,
                    sent_at TEXT NOT NULL
                )
            """)

            # Indices for fast lookups
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_offers_dates ON flight_offers (departure_date, return_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_offers_price ON flight_offers (price_idr)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_dates ON price_history (departure_date, return_date, price_idr)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts ON alerts_sent (airline, departure_date, return_date, price_idr, alert_type)")

            conn.commit()

    def record_search_run(self, origin: str, dest: str, travel_month: str, 
                          total_offers: int, lowest_price: Optional[float], 
                          status: str, notes: str = "") -> int:
        """Records a new search execution and returns the run ID."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO search_runs (run_timestamp, origin, destination, travel_month, total_offers_found, lowest_price_found, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (now, origin, dest, travel_month, total_offers, lowest_price, status, notes))
            conn.commit()
            return cursor.lastrowid

    def save_flight_offer(self, run_id: int, offer: Dict[str, Any]) -> int:
        """Stores a flight offer and adds an entry into price_history."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO flight_offers (
                    run_id, airline, flight_number, departure_date, return_date,
                    total_duration, transit_info, price_idr, cabin_baggage, checked_baggage,
                    booking_source, booking_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                offer.get("airline", "Unknown"),
                offer.get("flight_number", "N/A"),
                offer.get("departure_date"),
                offer.get("return_date"),
                offer.get("total_duration", "N/A"),
                offer.get("transit_info", "Direct"),
                offer.get("price_idr", 0.0),
                offer.get("cabin_baggage", "Standard 7kg"),
                offer.get("checked_baggage", "Not Included"),
                offer.get("booking_source", "Aggregator"),
                offer.get("booking_url", ""),
                now
            ))
            offer_id = cursor.lastrowid

            # Also track price history
            cursor.execute("""
                INSERT INTO price_history (airline, departure_date, return_date, price_idr, recorded_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                offer.get("airline", "Unknown"),
                offer.get("departure_date"),
                offer.get("return_date"),
                offer.get("price_idr", 0.0),
                now
            ))
            conn.commit()
            return offer_id

    def get_all_time_lowest_price(self, travel_month: str = "2027-11") -> Optional[Dict[str, Any]]:
        """Returns the lowest recorded price ever found for the given travel month."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM flight_offers 
                WHERE departure_date LIKE ? 
                ORDER BY price_idr ASC LIMIT 1
            """, (f"{travel_month}%",))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_previous_price(self, airline: str, departure_date: str, return_date: str) -> Optional[float]:
        """Gets the most recently recorded price prior to the current run for the same airline and dates."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT price_idr FROM price_history
                WHERE airline = ? AND departure_date = ? AND return_date = ?
                ORDER BY recorded_at DESC LIMIT 1 OFFSET 1
            """, (airline, departure_date, return_date))
            row = cursor.fetchone()
            if row:
                return row["price_idr"]
            
            # Fallback to any recent price for those exact dates
            cursor.execute("""
                SELECT price_idr FROM price_history
                WHERE departure_date = ? AND return_date = ?
                ORDER BY recorded_at DESC LIMIT 1 OFFSET 1
            """, (departure_date, return_date))
            fallback_row = cursor.fetchone()
            return fallback_row["price_idr"] if fallback_row else None

    def is_duplicate_alert(self, airline: str, departure_date: str, return_date: str, 
                           price_idr: float, alert_type: str) -> bool:
        """Checks if a matching alert was already dispatched to prevent spamming."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM alerts_sent
                WHERE airline = ? AND departure_date = ? AND return_date = ?
                  AND ABS(price_idr - ?) < 1.0 AND alert_type = ?
            """, (airline, departure_date, return_date, price_idr, alert_type))
            row = cursor.fetchone()
            return row["count"] > 0

    def record_alert_sent(self, offer_id: Optional[int], alert_type: str, 
                          airline: str, departure_date: str, return_date: str, 
                          price_idr: float, message_text: str):
        """Records an alert as successfully delivered."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alerts_sent (offer_id, alert_type, airline, departure_date, return_date, price_idr, message_text, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (offer_id, alert_type, airline, departure_date, return_date, price_idr, message_text, now))
            conn.commit()

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Aggregates metrics for the monitoring dashboard."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Last search run
            cursor.execute("SELECT * FROM search_runs ORDER BY id DESC LIMIT 1")
            last_run = cursor.fetchone()

            # All-time lowest price
            cursor.execute("SELECT * FROM flight_offers ORDER BY price_idr ASC LIMIT 1")
            lowest_offer = cursor.fetchone()

            # Total searches
            cursor.execute("SELECT COUNT(*) as total_runs FROM search_runs")
            total_runs = cursor.fetchone()["total_runs"]

            # Total alerts sent
            cursor.execute("SELECT COUNT(*) as total_alerts FROM alerts_sent")
            total_alerts = cursor.fetchone()["total_alerts"]

            # Recent alerts
            cursor.execute("SELECT * FROM alerts_sent ORDER BY id DESC LIMIT 5")
            recent_alerts = [dict(r) for r in cursor.fetchall()]

            # Recent price history
            cursor.execute("""
                SELECT airline, departure_date, return_date, price_idr, recorded_at 
                FROM price_history ORDER BY id DESC LIMIT 10
            """)
            recent_prices = [dict(r) for r in cursor.fetchall()]

            return {
                "last_run": dict(last_run) if last_run else None,
                "lowest_offer": dict(lowest_offer) if lowest_offer else None,
                "total_runs": total_runs,
                "total_alerts": total_alerts,
                "recent_alerts": recent_alerts,
                "recent_prices": recent_prices
            }

db = Database()
