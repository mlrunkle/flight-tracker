from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import datetime
import pandas as pd
import config
import os
import json

def get_credentials():
    """Get credentials from either local file or Streamlit secrets"""
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
            # Running on Streamlit Cloud - use secrets
            return Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]),
                scopes=['https://www.googleapis.com/auth/calendar.readonly']
            )
    except:
        pass
    
    # Running locally - use service account file
    if os.path.exists(config.SERVICE_ACCOUNT_FILE):
        return Credentials.from_service_account_file(
            config.SERVICE_ACCOUNT_FILE,
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
    else:
        raise RuntimeError("No credentials found. Set up Streamlit secrets or add service account JSON file.")

def get_travel_events():
    try:
        creds = get_credentials()
        service = build('calendar', 'v3', credentials=creds)

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
        raise RuntimeError(f"Calendar API error: {e}")

    rows = []
    for e in events:
        start = e['start'].get('dateTime', e['start'].get('date'))
        end = e['end'].get('dateTime', e['end'].get('date'))
        rows.append({'Event': e.get('summary', ''), 'Start': start, 'End': end})
    return pd.DataFrame(rows)
