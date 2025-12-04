from google.cloud import storage
from google.oauth2 import service_account
import config
import datetime
import json
import os

def get_storage_client():
    """Get GCP storage client from either local file or Streamlit secrets"""
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
            # Running on Streamlit Cloud - use secrets
            credentials = service_account.Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"])
            )
            return storage.Client(credentials=credentials)
    except:
        pass
    
    # Running locally - use service account file
    if os.path.exists(config.SERVICE_ACCOUNT_FILE):
        return storage.Client.from_service_account_json(config.SERVICE_ACCOUNT_FILE)
    else:
        raise RuntimeError("No GCP credentials found. Set up Streamlit secrets or add service account JSON file.")

def upload_results(results_json: dict, prefix='serpapi_results'):
    try:
        client = get_storage_client()
        bucket = client.get_bucket(config.BUCKET_NAME)

        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')
        blob_path = f"{config.BUCKET_PATH}{prefix}_{timestamp}.json"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json.dumps(results_json), content_type='application/json')
    except Exception as e:
        raise RuntimeError(f"GCP storage error: {e}")
    return blob_path