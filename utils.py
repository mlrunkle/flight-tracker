import re

def extract_airport_codes(event_summary: str):
    codes = re.findall(r"[A-Z]{3}", event_summary)
    if len(codes) >= 2:
        return codes[0], codes[1]
    return 'DFW', codes[0] if codes else 'QRO'