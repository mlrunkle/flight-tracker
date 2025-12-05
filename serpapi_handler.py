from serpapi import GoogleSearch
import config

def search_flights(departure_id, arrival_id, outbound_date, return_date, stops=0):
    params = {
        'engine': 'google_flights',
        'api_key': config.SERPAPI_KEY,
        'departure_id': departure_id,
        'arrival_id': arrival_id,
        'outbound_date': outbound_date.split('T')[0],
        'return_date': return_date.split('T')[0],
        'hl': 'en',
        'gl': 'us',
        'currency': 'USD'
    }
    # Add stops parameter if not default (0 = any)
    if stops > 0:
        params['stops'] = stops
    
    try:
        search = GoogleSearch(params)
        return search.get_dict()
    except Exception as e:
        raise RuntimeError(f"SerpAPI error: {e}")