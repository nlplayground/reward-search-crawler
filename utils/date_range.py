def date_range(days=360):
    from datetime import date, timedelta

    today = date.today()
    for i in range(days + 1):
        yield (today + timedelta(days=i)).isoformat()