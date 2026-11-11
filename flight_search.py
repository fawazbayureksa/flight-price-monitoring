"""
Flight Search module for CGK (Jakarta) -> CTS (Sapporo, Japan).
Queries legitimate flight data sources (Amadeus API, SerpApi/Google Flights, Aggregators)
and generates deep booking links while respecting airline schedule horizons (330-360 days).
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, date
from typing import List, Dict, Any, Optional

from config import settings, logger

class FlightSearchService:
    def __init__(self):
        self.origin = settings.origin
        self.destination = settings.destination
        self.year = settings.travel_year
        self.month = settings.travel_month

    def get_sample_date_pairs(self) -> List[Dict[str, str]]:
        """
        Generates standard round-trip date combinations across November 2027:
        - 10-day, 12-day, and 14-day holiday durations.
        """
        pairs = [
            {"departure": f"{self.year}-11-05", "return": f"{self.year}-11-15", "desc": "Nov 5 - Nov 15 (10 days)"},
            {"departure": f"{self.year}-11-10", "return": f"{self.year}-11-20", "desc": "Nov 10 - Nov 20 (10 days)"},
            {"departure": f"{self.year}-11-12", "return": f"{self.year}-11-24", "desc": "Nov 12 - Nov 24 (12 days)"},
            {"departure": f"{self.year}-11-15", "return": f"{self.year}-11-25", "desc": "Nov 15 - Nov 25 (10 days)"},
            {"departure": f"{self.year}-11-18", "return": f"{self.year}-11-28", "desc": "Nov 18 - Nov 28 (10 days)"},
            {"departure": f"{self.year}-11-01", "return": f"{self.year}-11-15", "desc": "Nov 1 - Nov 15 (14 days)"},
            {"departure": f"{self.year}-11-16", "return": f"{self.year}-11-30", "desc": "Nov 16 - Nov 30 (14 days)"},
        ]
        return pairs

    def build_google_flights_url(self, departure_date: str, return_date: str) -> str:
        """Constructs a direct Google Flights search deep link."""
        return (
            f"https://www.google.com/travel/flights?q=Flights%20to%20{self.destination}%20from%20{self.origin}%20"
            f"on%20{departure_date}%20through%20{return_date}&curr=IDR"
        )

    def build_skyscanner_url(self, departure_date: str, return_date: str) -> str:
        """Constructs a Skyscanner round-trip search link."""
        dep_formatted = departure_date.replace("-", "")[2:]  # YYMMDD
        ret_formatted = return_date.replace("-", "")[2:]
        return f"https://www.skyscanner.co.id/transport/flights/{self.origin.lower()}/{self.destination.lower()}/{dep_formatted}/{ret_formatted}/?adultsv2=1&cabinclass=economy&currency=IDR"

    def build_traveloka_url(self, departure_date: str, return_date: str) -> str:
        """Constructs a Traveloka round-trip search link."""
        d_split = departure_date.split("-")
        r_split = return_date.split("-")
        dep_str = f"{d_split[2]}-{d_split[1]}-{d_split[0]}"
        ret_str = f"{r_split[2]}-{r_split[1]}-{r_split[0]}"
        return f"https://www.traveloka.com/en-id/flight/fullsearch?ap={self.origin}.{self.destination}&dt={dep_str}.{ret_str}&ps=1.0.0&sc=ECONOMY"

    def check_booking_horizon(self, target_date_str: str) -> Dict[str, Any]:
        """
        Evaluates whether the requested target date falls within the standard GDS
        airline schedule window (typically ~330 to 360 days in advance).
        """
        today = date.today()
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        days_ahead = (target_date - today).days

        is_open_gds = days_ahead <= 360
        is_open_lcc = days_ahead <= 300

        return {
            "today": str(today),
            "target_date": target_date_str,
            "days_ahead": days_ahead,
            "gds_horizon_status": "OPEN (330-360d range)" if is_open_gds else f"AHEAD ({days_ahead} days away, opens ~330-360d out)",
            "lcc_horizon_status": "OPEN" if is_open_lcc else f"AHEAD ({days_ahead} days away, opens ~180-300d out)"
        }

    def search_amadeus(self, departure_date: str, return_date: str) -> List[Dict[str, Any]]:
        """
        Searches Amadeus Flight Offers API if credentials are provided in .env.
        Reports limitations cleanly without fabricating prices.
        """
        if not settings.amadeus_client_id or not settings.amadeus_client_secret:
            logger.info("Amadeus API credentials not configured in .env. Skipping Amadeus lookup.")
            return []

        logger.info(f"Connecting to Amadeus API for {self.origin} -> {self.destination} ({departure_date} to {return_date})...")
        try:
            # 1. Obtain OAuth2 Token
            token_url = "https://test.api.amadeus.com/v1/security/oauth2/token"
            auth_data = urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": settings.amadeus_client_id,
                "client_secret": settings.amadeus_client_secret
            }).encode("utf-8")
            
            token_req = urllib.request.Request(token_url, data=auth_data)
            with urllib.request.urlopen(token_req, timeout=10) as resp:
                token_json = json.loads(resp.read().decode("utf-8"))
                access_token = token_json.get("access_token")

            # 2. Flight Offers Search
            search_url = (
                f"https://test.api.amadeus.com/v2/shopping/flight-offers?"
                f"originLocationCode={self.origin}&destinationLocationCode={self.destination}&"
                f"departureDate={departure_date}&returnDate={return_date}&"
                f"adults={settings.passengers}&travelClass={settings.cabin_class}&"
                f"currencyCode=IDR&max=5"
            )
            req = urllib.request.Request(search_url, headers={"Authorization": f"Bearer {access_token}"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                search_data = json.loads(resp.read().decode("utf-8"))
                offers = []
                for item in search_data.get("data", []):
                    price_val = float(item["price"]["total"])
                    itineraries = item.get("itineraries", [])
                    outbound = itineraries[0] if len(itineraries) > 0 else {}
                    segments = outbound.get("segments", [])
                    airline_code = segments[0].get("carrierCode", "Unknown") if segments else "Multiple"
                    duration = outbound.get("duration", "N/A").replace("PT", "").lower()
                    stops = len(segments) - 1
                    transit = "Direct" if stops == 0 else f"{stops} stop(s)"

                    offers.append({
                        "airline": airline_code,
                        "flight_number": f"{airline_code} {segments[0].get('number', '')}" if segments else "N/A",
                        "departure_date": departure_date,
                        "return_date": return_date,
                        "total_duration": duration,
                        "transit_info": transit,
                        "price_idr": price_val,
                        "cabin_baggage": "Standard 7kg",
                        "checked_baggage": "Included" if "checkedBags" in item.get("pricingOptions", {}) else "Not Included",
                        "booking_source": "Amadeus GDS",
                        "booking_url": self.build_google_flights_url(departure_date, return_date)
                    })
                return offers
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            logger.warning(f"Amadeus API returned HTTP {e.code}: {err_msg}")
            return []
        except Exception as e:
            logger.error(f"Error querying Amadeus API: {e}")
            return []

    def search_all_sources(self) -> Dict[str, Any]:
        """
        Executes search across configured flight data sources and date pairs.
        Returns a dict containing discovered offers, status, horizon check, and direct search links.
        """
        date_pairs = self.get_sample_date_pairs()
        first_pair = date_pairs[0]
        horizon_info = self.check_booking_horizon(first_pair["departure"])

        all_offers = []
        links_generated = []

        for pair in date_pairs:
            dep = pair["departure"]
            ret = pair["return"]
            gf_link = self.build_google_flights_url(dep, ret)
            sky_link = self.build_skyscanner_url(dep, ret)
            tvl_link = self.build_traveloka_url(dep, ret)

            links_generated.append({
                "period": pair["desc"],
                "departure": dep,
                "return": ret,
                "google_flights": gf_link,
                "skyscanner": sky_link,
                "traveloka": tvl_link
            })

            # Check Amadeus API if credentials exist
            amadeus_offers = self.search_amadeus(dep, ret)
            all_offers.extend(amadeus_offers)

        notes = (
            f"Searched {len(date_pairs)} date pairs for November 2027. "
            f"Current booking horizon: {horizon_info['days_ahead']} days out ({horizon_info['gds_horizon_status']}). "
            f"Direct search aggregator deep-links generated for real-time verification."
        )

        return {
            "status": "SUCCESS",
            "horizon": horizon_info,
            "offers": all_offers,
            "verification_links": links_generated,
            "notes": notes
        }

    @staticmethod
    def get_sample_test_offers() -> List[Dict[str, Any]]:
        """
        Provides realistic baseline market data for CGK -> CTS for validation
        and testing of the comparison engine, threshold trigger, and Telegram alert pipeline.
        Reflects real airline routes operating between Jakarta and Sapporo:
        - Scoot (via Singapore SIN)
        - VietJet Air (via Ho Chi Minh SGN or Hanoi HAN)
        - AirAsia (via Kuala Lumpur KUL)
        - Philippine Airlines (via Manila MNL)
        - Cathay Pacific (via Hong Kong HKG)
        """
        return [
            {
                "airline": "Scoot",
                "flight_number": "TR-277 / TR-892",
                "departure_date": "2027-11-05",
                "return_date": "2027-11-15",
                "total_duration": "14h 25m (Out) / 15h 10m (Ret)",
                "transit_info": "1 Stop via Singapore (SIN)",
                "price_idr": 6980000.0,
                "cabin_baggage": "Cabin 10kg (FlyBag)",
                "checked_baggage": "20kg Included (FlyBag)",
                "booking_source": "Scoot Official / Google Flights",
                "booking_url": "https://www.google.com/travel/flights?q=Flights%20to%20CTS%20from%20CGK%20on%202027-11-05%20through%202027-11-15&curr=IDR"
            },
            {
                "airline": "VietJet Air",
                "flight_number": "VJ-854 / VJ-932",
                "departure_date": "2027-11-10",
                "return_date": "2027-11-20",
                "total_duration": "13h 50m (Out) / 14h 30m (Ret)",
                "transit_info": "1 Stop via Ho Chi Minh City (SGN)",
                "price_idr": 6450000.0,
                "cabin_baggage": "Cabin 7kg",
                "checked_baggage": "Not Included (Available from +IDR 650.000)",
                "booking_source": "VietJet Direct / Skyscanner",
                "booking_url": "https://www.google.com/travel/flights?q=Flights%20to%20CTS%20from%20CGK%20on%202027-11-10%20through%202027-11-20&curr=IDR"
            },
            {
                "airline": "AirAsia",
                "flight_number": "QZ-202 / D7-550",
                "departure_date": "2027-11-15",
                "return_date": "2027-11-25",
                "total_duration": "15h 30m (Out) / 16h 00m (Ret)",
                "transit_info": "1 Stop via Kuala Lumpur (KUL)",
                "price_idr": 7250000.0,
                "cabin_baggage": "Cabin 7kg",
                "checked_baggage": "Not Included (Optional 20kg Pack)",
                "booking_source": "AirAsia Superapp / Google Flights",
                "booking_url": "https://www.google.com/travel/flights?q=Flights%20to%20CTS%20from%20CGK%20on%202027-11-15%20through%202027-11-25&curr=IDR"
            },
            {
                "airline": "Philippine Airlines",
                "flight_number": "PR-536 / PR-408",
                "departure_date": "2027-11-18",
                "return_date": "2027-11-28",
                "total_duration": "13h 15m (Out) / 14h 10m (Ret)",
                "transit_info": "1 Stop via Manila (MNL)",
                "price_idr": 7450000.0,
                "cabin_baggage": "Cabin 7kg",
                "checked_baggage": "23kg Included",
                "booking_source": "Philippine Airlines / Skyscanner",
                "booking_url": "https://www.google.com/travel/flights?q=Flights%20to%20CTS%20from%20CGK%20on%202027-11-18%20through%202027-11-28&curr=IDR"
            }
        ]

flight_service = FlightSearchService()
