from datetime import datetime, timedelta
import json

def date_range(days=360, start=0, end=None):
    from datetime import date, timedelta
    today = date.today()
    if not end:
        end = days
    for i in range(start, end):
        yield (today + timedelta(days=i)).isoformat()

def date_add(days=0, date_str=None):
    """
    Equivalent to JS dateAdd(days, date)
    date_str is expected in 'YYYYMMDD' format (e.g. '20251018')
    Returns a new date string in the same format.
    """
    if date_str:
        year = int(date_str[0:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        new_date = datetime(year, month, day)
    else:
        new_date = datetime.now()

    new_date += timedelta(days=days)
    return new_date.strftime("%Y%m%d")

def deep_json_load(obj):
    """
    Recursively convert JSON strings to dicts/lists wherever possible.
    """
    if isinstance(obj, str):
        try:
            # Try parsing the string as JSON
            parsed = json.loads(obj)
            return deep_json_load(parsed)  # recurse in case it's nested further
        except json.JSONDecodeError:
            return obj  # not a JSON string, return as-is
    elif isinstance(obj, dict):
        return {k: deep_json_load(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_json_load(item) for item in obj]
    else:
        return obj  # primitive type