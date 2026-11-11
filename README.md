# Flight Price Monitoring Automation
## CGK (Jakarta) → CTS (Sapporo, Japan) | November 2027

An automated flight price monitoring system that monitors round-trip flights from **Soekarno-Hatta International Airport (CGK)**, Jakarta, Indonesia to **New Chitose Airport (CTS)**, Sapporo, Japan for travel during **November 1–30, 2027** with a budget threshold of **IDR 7,500,000 per passenger**.

---

### 1. Features
- **Accurate Flight Tracking**: Integrates with live GDS (Amadeus API) and aggregates direct deep links into Google Flights, Skyscanner, and Traveloka.
- **Schedule Horizon Intelligence**: Monitors the 330–360 day airline booking horizon. When November 2027 schedules load into GDS/airline booking systems, fares are immediately captured.
- **Price Trend & History Tracking**: Stores all search runs, price points, and historical trends in an embedded SQLite database (`flight_tracker.db`).
- **Smart Alert Triggers**:
  1. Ticket available at or under target budget (**≤ IDR 7,500,000**).
  2. Significant price drop (**≥ 5% decrease** from previous recorded fare).
  3. New all-time lowest price discovered.
- **Telegram Notification Integration**:
  - Connects to Telegram Bot `@RexxTripHunterBot`.
  - Dispatches messages in the exact user-specified format with live savings, transit details, baggage allowances, booking links, and WIB timestamp.
  - **Duplicate Prevention**: Tracks delivered alerts to prevent repeated notifications for identical flights/prices.
  - **Security**: Sensitive bot tokens are managed via `.env` and masked in logs.
- **Built-in Dashboard**: Terminal dashboard displaying last run status, current lowest fare, budget delta, historical trends, and notification history.

---

### 2. Architecture & Directory Structure

```
flight-tracker-cgk-cts/
├── .env                  # Configuration & bot credentials (never commit tokens)
├── config.py             # Settings loader & sensitive data log sanitizer
├── database.py           # SQLite database schema and persistence layer
├── flight_search.py      # GDS/Aggregator search & booking link generator
├── price_analyzer.py     # Budget, drop, and lowest-fare evaluation engine
├── notifier.py           # Telegram notification builder and API sender
├── dashboard.py          # Terminal monitoring and reporting dashboard
├── main.py               # CLI entry point (run-once, schedule, test, dashboard)
├── flight_tracker.db     # SQLite persistence database (auto-generated)
├── flight_tracker.log    # Search execution logs (auto-generated)
└── README.md             # Documentation and usage guide
```

---

### 3. Telegram Setup (Important First Step)

1. Open Telegram on your phone or desktop.
2. Search for the bot: **`@RexxTripHunterBot`** (or go to `https://t.me/RexxTripHunterBot`).
3. Press **Start** (send `/start`).
   > *Telegram security requires users to initiate a conversation before a bot can send messages to their chat ID (`1255250687`).*
4. Run the test command to verify message delivery:
   ```powershell
   cd C:\Users\ASUS-PC\.gemini\antigravity\scratch\flight-tracker-cgk-cts
   python main.py --test-telegram
   ```

---

### 4. CLI Usage

#### Execute a Live Search Run
```powershell
python main.py --run-once
```

#### View the Monitoring Dashboard
```powershell
python main.py --dashboard
```

#### Test Price Drop & Alert Flow with Baseline Route Data
```powershell
python main.py --simulate-sample
```

#### Run the Daily Continuous Scheduler (09:00 WIB)
```powershell
python main.py --schedule
```

---

### 5. Scheduled Automation (Antigravity Sidecar)

The automation is configured as a background scheduled sidecar:
- **Automation Name**: `CGK to Sapporo Flight Price Tracker`
- **Schedule**: `CRON_TZ=Asia/Jakarta 0 9 * * *` (Daily at 09:00 AM WIB)
- **Sidecar File**: `~/.gemini/config/sidecars/cgk-sapporo-flight-tracker/sidecar.json`
- **Enabling**: Open the Automations dashboard and toggle the automation on.
