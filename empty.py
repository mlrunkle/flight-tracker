# streamlit_app.py
import json
import time
import pathlib
import datetime
from typing import Any, Dict, Tuple, Optional, List
from concurrent.futures import ThreadPoolExecutor

import requests
import pandas as pd
import streamlit as st
import altair as alt

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config  # expects keys noted previously


st.set_page_config(page_title="Flight Price Monitor", page_icon="✈️", layout="wide")
st.title("✈️ Flight Price Monitor (Calendar → SerpAPI)")
DATA_DIR = pathlib.Path("data"); DATA_DIR.mkdir(exist_ok=True)


def get_travel_events():
    try:
        creds = Credentials.from_service_account_file(
            config.SERVICE_ACCOUNT_FILE,
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)

        now = datetime.datetime.utcnow().isoformat() + 'Z'
        one_year = (datetime.datetime.utcnow() + datetime.timedelta(days=365)).isoformat() + 'Z'

        response = service.events().list(
            calendarId=config.CALENDAR_ID,
            timeMin=now,
            timeMax=one_year,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = response.get('items', [])
    except Exception as e:
        st.stop() if st.error(f"Calendar API error: {e}") else None

    rows = []
    for e in events:
        start = e['start'].get('dateTime', e['start'].get('date'))
        end = e['end'].get('dateTime', e['end'].get('date'))
        rows.append({'Event': e.get('summary', ''), 'Start': start, 'End': end})
    return pd.DataFrame(rows)


def _normalize_event_dates(start_raw: str, end_raw: str) -> Tuple[str, str]:
    def to_date(s: str) -> datetime.date:
        return datetime.date.fromisoformat(s[:10]) if "T" in s else datetime.date.fromisoformat(s)
    s_date, e_date = to_date(start_raw), to_date(end_raw)
    if "T" not in start_raw and "T" not in end_raw:
        e_date = e_date - datetime.timedelta(days=1)
    if e_date < s_date:
        e_date = s_date
    return s_date.isoformat(), e_date.isoformat()


SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

@st.cache_data(ttl=60*60, show_spinner=False)
def fetch_route_json(
    api_key: str,
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    return_date: Optional[str],
    hl: str,
    gl: str,
    currency: str,
    stops: int,                 # <-- NEW: cache key includes stops
    cache_bust: int = 0,
) -> Dict[str, Any]:
    params = {
        "engine": "google_flights",
        "api_key": api_key,
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "hl": hl,
        "gl": gl,
        "currency": currency,
        "stops": stops,         # <-- NEW
    }
    if return_date:
        params["return_date"] = return_date
    r = requests.get(SERPAPI_ENDPOINT, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def extract_lowest_price(payload: Dict[str, Any]) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    candidates: List[Tuple[Optional[float], Optional[str], Optional[str]]] = []

    def parse_money(s: str) -> Tuple[Optional[float], Optional[str]]:
        if not s: return None, None
        cur = "USD" if ("USD" in s.upper() or "$" in s) else ("EUR" if ("EUR" in s.upper() or "€" in s) else ("GBP" if ("GBP" in s.upper() or "£" in s) else None))
        digits = "".join(ch for ch in s if (ch.isdigit() or ch == "."))
        try: return float(digits), cur
        except: return None, cur

    def harvest(list_key: str):
        for f in payload.get(list_key, []) or []:
            price_raw = f.get("price") or f.get("price_total") or f.get("price_display") or ""
            amount, cur = parse_money(str(price_raw))
            airline = None
            if isinstance(f.get("airlines"), list) and f["airlines"]:
                airline = ", ".join(f["airlines"][:2])
            elif f.get("airline"):
                airline = f["airline"]
            elif f.get("legs"):
                try:
                    airline = f["legs"][0].get("airline") or f["legs"][0].get("operating_carrier")
                except Exception:
                    pass
            if amount is not None:
                candidates.append((amount, cur, airline))

    for key in ("best_flights", "other_flights", "prices", "results"):
        harvest(key)
    for k in ("lowest_price", "minimum_price"):
        v = payload.get(k)
        if isinstance(v, (int, float)):
            candidates.append((float(v), None, None))
        elif isinstance(v, str):
            amt, cur = parse_money(v)
            if amt is not None:
                candidates.append((amt, cur, None))
    if not candidates: return None, None, None
    candidates.sort(key=lambda x: x[0])
    return candidates[0]


def save_json(payload: Dict[str, Any], departure: str, dest: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DATA_DIR / f"{ts}_{departure}_to_{dest}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(path)


with st.sidebar:
    st.header("Settings")
    st.caption("Override defaults from config.py as needed.")

    departure_airport = st.text_input(
        "Departure airport (IATA)", value=getattr(config, "DEPARTURE_AIRPORT", "OKC")
    )

    default_dests = ", ".join(getattr(
        config, "DESTINATION_AIRPORTS",
        ["LAX","SFO","SEA","JFK","BOS","MIA","ORD","DEN","DFW","ATL"]
    ))
    dest_text = st.text_area("Destination airports (comma-separated, max 10)", value=default_dests, height=100)
    destinations = [d.strip().upper() for d in dest_text.split(",") if d.strip()][:10]

    calendar_query = st.text_input("Filter events by text (optional)", value=str(getattr(config, "CALENDAR_QUERY", "") or ""))

    # NEW: Stops selector (maps to SerpAPI's 0..3 values)
    stops_label_to_value = {
        "Any (default)": 0,
        "Nonstop only": 1,
        "≤ 1 stop": 2,
        "≤ 2 stops": 3,
    }
    stops_choice = st.selectbox("Number of stops", list(stops_label_to_value.keys()), index=0,
                                help="Filters flights by stops via SerpAPI `stops` parameter.")
    stops_value = stops_label_to_value[stops_choice]

    concurrency = st.slider("Parallel requests", min_value=1, max_value=6, value=3)
    throttle_s = st.slider("Delay between requests (seconds)", min_value=0.0, max_value=2.0, value=0.5, step=0.1)
    force_refresh = st.checkbox("Force refresh (bypass cache)", value=False)

    st.divider()
    st.markdown("**SerpAPI:** Key read from `config.SERPAPI_KEY`.")
    st.markdown("**Google Calendar:** Uses `config.SERVICE_ACCOUNT_FILE` and `config.CALENDAR_ID`.")


with st.spinner("Fetching upcoming events..."):
    try:
        events_df = get_travel_events()
    except Exception as e:
        st.error(f"Failed to read calendar events: {e}"); st.stop()

if calendar_query:
    events_df = events_df[events_df["Event"].fillna("").str.contains(calendar_query, case=False, na=False)]
if events_df.empty:
    st.info("No upcoming events found (within 1 year) that match your filter."); st.stop()

def label_row(r: pd.Series) -> str:
    out, ret = _normalize_event_dates(str(r["Start"]), str(r["End"]))
    return f"{out} → {ret} — {r['Event'] or '(untitled)'}"

event_idx = st.selectbox(
    "Choose an event to use for dates",
    options=list(range(len(events_df))),
    format_func=lambda i: label_row(events_df.iloc[i]),
    index=0
)
chosen = events_df.iloc[event_idx]
event_title = str(chosen["Event"] or "(untitled)")
outbound_date, return_date = _normalize_event_dates(str(chosen["Start"]), str(chosen["End"]))

c1, c2, c3 = st.columns([1,1,3])
with c1: st.write("**Outbound:**", outbound_date)
with c2: st.write("**Return:**", return_date)
with c3: st.write("**Event:**", event_title)
st.divider()

run = st.button("🔎 Search prices")

if run:
    if not getattr(config, "SERPAPI_KEY", None):
        st.error("SERPAPI_KEY missing in config.py"); st.stop()
    if not departure_airport or not destinations:
        st.error("Please provide a departure airport and at least one destination."); st.stop()

    st.subheader("Results")
    progress = st.progress(0, text="Starting requests...")
    rows: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = []
        for i, dest in enumerate(destinations):
            if i > 0 and throttle_s > 0:
                time.sleep(throttle_s)
            futures.append((dest, ex.submit(
                fetch_route_json,
                config.SERPAPI_KEY,
                departure_airport,
                dest,
                outbound_date,
                return_date,
                "en", "us", "USD",
                stops_value,                  # <-- NEW
                1 if force_refresh else 0
            )))

        for idx, (dest, fut) in enumerate(futures, start=1):
            try:
                payload = fut.result()
                json_path = save_json(payload, departure_airport, dest)
                low, cur, airline = extract_lowest_price(payload)
                rows.append({
                    "event": event_title,
                    "departure": departure_airport,
                    "destination": dest,
                    "outbound_date": outbound_date,
                    "return_date": return_date,
                    "stops_filter": stops_choice,   # <-- NEW (for visibility in table)
                    "lowest_price": low,
                    "currency": cur or "USD",
                    "sample_airline": airline,
                    "json_file": json_path
                })
            except requests.HTTPError as e:
                rows.append({
                    "event": event_title, "departure": departure_airport, "destination": dest,
                    "outbound_date": outbound_date, "return_date": return_date,
                    "stops_filter": stops_choice,
                    "lowest_price": None, "currency": None, "sample_airline": None,
                    "json_file": None, "error": f"HTTPError: {e}"
                })
            except Exception as e:
                rows.append({
                    "event": event_title, "departure": departure_airport, "destination": dest,
                    "outbound_date": outbound_date, "return_date": return_date,
                    "stops_filter": stops_choice,
                    "lowest_price": None, "currency": None, "sample_airline": None,
                    "json_file": None, "error": str(e)
                })
            progress.progress(idx / len(futures), text=f"Fetched {idx}/{len(futures)}")

    progress.empty()
    df = pd.DataFrame(rows).sort_values(by=["lowest_price", "destination"], ascending=[True, True], na_position="last")
    st.dataframe(df, use_container_width=True, height=min(600, 100 + 35 * max(1, len(df))))

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV",
        data=csv_bytes,
        file_name=f"summary_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

    chart_df = df.dropna(subset=["lowest_price"]).copy()
    if not chart_df.empty:
        st.subheader("Price comparison")
        chart = (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X("destination:N", sort="-y", title="Destination"),
                y=alt.Y("lowest_price:Q", title="Lowest price (≈ currency shown)"),
                tooltip=["destination", "lowest_price", "sample_airline", "stops_filter"]
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)

    err_rows = df[df["error"].notna()] if "error" in df.columns else pd.DataFrame()
    if not err_rows.empty:
        with st.expander("Errors"):
            st.dataframe(err_rows[["destination", "error"]], use_container_width=True)
else:
    st.info("Pick an event, choose stops/airports, then click **Search prices**.")
