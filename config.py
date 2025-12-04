# SerpAPI - will be overridden by Streamlit secrets in production
SERPAPI_KEY = '6f18bf9e6073d3b3903119e8577e6cd9463e82f7fefd8ae279b3487f234fe339'

# Google Calendar - will be overridden by Streamlit secrets in production
SERVICE_ACCOUNT_FILE = 'flighttracker-443304-f0b91944972b.json'
CALENDAR_ID = 'v6dnr8u7d9b29ice0suf3un8tg@group.calendar.google.com'

# GCP Storage - will be overridden by Streamlit secrets in production
BUCKET_NAME = 'ft_ingestion'
BUCKET_PATH = 'serpapi_results/serpapi/'

# Flight Search Defaults
DEFAULT_DEPARTURE = 'DFW'
DEFAULT_DESTINATIONS = [
    'LAX',  # Los Angeles
    'NYC',  # New York City
    'MIA',  # Miami
    'LAS',  # Las Vegas
    'SEA',  # Seattle
    'DEN',  # Denver
    'ORD',  # Chicago
    'BOS',  # Boston
    'SFO',  # San Francisco
    'ATL',  # Atlanta
]

# Load from Streamlit secrets when deployed
try:
    import streamlit as st
    if hasattr(st, 'secrets'):
        SERPAPI_KEY = st.secrets.get("SERPAPI_KEY", SERPAPI_KEY)
        CALENDAR_ID = st.secrets.get("CALENDAR_ID", CALENDAR_ID)
        BUCKET_NAME = st.secrets.get("BUCKET_NAME", BUCKET_NAME)
        BUCKET_PATH = st.secrets.get("BUCKET_PATH", BUCKET_PATH)
except:
    pass  # Running locally, use defaults above
