from calendar import monthrange
from datetime import date, timedelta

from fastapi import HTTPException


def resolve_period(
    date_from: date | None,
    date_to: date | None,
    month: str | None,
) -> tuple[date | None, date | None]:
    if month:
        try:
            year, month_number = (int(value) for value in month.split("-", 1))
            if not 1 <= month_number <= 12:
                raise ValueError
            month_from = date(year, month_number, 1)
            month_to = date(year, month_number, monthrange(year, month_number)[1])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="month must use YYYY-MM format")
        if date_from or date_to:
            raise HTTPException(status_code=400, detail="Use month or date_from/date_to, not both")
        return month_from, month_to

    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")
    return date_from, date_to


def holiday_summary(date_from, date_to, holidays):
    if not date_from or not date_to:
        return 0, None, []

    holiday_by_date = {holiday.date: holiday for holiday in holidays}
    current = date_from
    holiday_details = []
    while current <= date_to:
        if current in holiday_by_date:
            holiday = holiday_by_date[current]
            holiday_details.append({
                "date": current,
                "reason": holiday.reason,
                "type": "special",
                "id": holiday.id,
            })
        elif current.weekday() == 6:
            holiday_details.append({
                "date": current,
                "reason": "Sunday",
                "type": "sunday",
            })
        current += timedelta(days=1)

    total_days = (date_to - date_from).days + 1
    return len(holiday_details), total_days - len(holiday_details), holiday_details
