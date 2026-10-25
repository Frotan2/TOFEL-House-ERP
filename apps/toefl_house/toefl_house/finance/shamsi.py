"""Afghan Solar Hijri civil-date boundaries for accounting and teaching.

A pure conversion/period utility; native Frappe/ERPNext posting dates stay ISO.
The Solar Hijri year begins at the March equinox; the Jalaali break-year
algorithm (jalaali-js/MIT, based on Kazimierz Borkowski) determines Nowruz.
Bounded to 1300..1499 AH to avoid silently using an unverified far-future
astronomical prediction. Customer reports must label the dates explicitly.
Never change historical GL posting dates when changing display calendars.
"""
from datetime import date, timedelta

MONTH_NAMES = (
    "حمل", "ثور", "جوزا", "سرطان", "اسد", "سنبله",
    "میزان", "عقرب", "قوس", "جدی", "دلو", "حوت",
)
_BREAKS = (
    -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
    1215, 1983, 2060, 2097, 2192, 2262, 2324, 2386, 2456, 3178,
)
MIN_YEAR, MAX_YEAR = 1300, 1499


def _integer(value, what):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{what} must be an integer")
    return value


def _nowruz(year):
    """Gregorian start of a Solar Hijri year, calculated without locale."""
    jy = _integer(year, "Solar Hijri year")
    if not MIN_YEAR <= jy <= MAX_YEAR:
        raise ValueError(f"Solar Hijri year outside supported {MIN_YEAR}-{MAX_YEAR} range")
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for jm in _BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += (jump // 33) * 8 + (jump % 33) // 4
        jp = jm
    n = jy - jp
    leap_j += (n // 33) * 8 + ((n % 33) + 3) // 4
    if jump % 33 == 4 and jump - n == 4:
        leap_j += 1
    leap_g = gy // 4 - ((gy // 100 + 1) * 3) // 4 - 150
    return date(gy, 3, 20 + leap_j - leap_g)


def is_leap_year(year):
    year = _integer(year, "Solar Hijri year")
    if year >= MAX_YEAR:
        raise ValueError("Cannot check last supported year's leap boundary")
    return (_nowruz(year + 1) - _nowruz(year)).days == 366


def days_in_month(year, month):
    month = _integer(month, "Solar Hijri month")
    if not 1 <= month <= 12:
        raise ValueError("Solar Hijri month must be 1-12")
    _nowruz(year)
    return 31 if month <= 6 else 30 if month <= 11 else 30 if is_leap_year(year) else 29


def shamsi_to_gregorian(year, month, day):
    month = _integer(month, "Solar Hijri month")
    day = _integer(day, "Solar Hijri day")
    if not 1 <= day <= days_in_month(year, month):
        raise ValueError("Solar Hijri date has an invalid day")
    offset = (month - 1) * 31 if month <= 6 else 186 + (month - 7) * 30
    return _nowruz(year) + timedelta(days=offset + day - 1)


def gregorian_to_shamsi(value):
    """Return (year, month, day) for an ISO date or datetime.date."""
    day = date.fromisoformat(value) if isinstance(value, str) else value
    if type(day) is not date:
        raise ValueError("Posting date must be an ISO date or datetime.date")
    jy = day.year - 621
    if jy < MIN_YEAR:
        jy = MIN_YEAR
    if jy > MAX_YEAR:
        raise ValueError("Date outside supported Solar Hijri range")
    if day < _nowruz(jy):
        jy -= 1
    if not MIN_YEAR <= jy <= MAX_YEAR:
        raise ValueError("Date outside supported Solar Hijri range")
    ordinal = (day - _nowruz(jy)).days
    if ordinal < 186:
        return jy, ordinal // 31 + 1, ordinal % 31 + 1
    ordinal -= 186
    return jy, ordinal // 30 + 7, ordinal % 30 + 1


def parse_shamsi_month(value):
    """Strict YYYY-MM period key (four ASCII year digits, two month digits)."""
    if not isinstance(value, str) or len(value) != 7 or value[4] != "-" or (
        not value[:4].isascii() or not value[:4].isdigit()
        or not value[5:].isascii() or not value[5:].isdigit()
    ):
        raise ValueError("Solar Hijri period must be YYYY-MM")
    year, month = int(value[:4]), int(value[5:])
    days_in_month(year, month)
    return year, month


def month_key(value):
    year, month, _ = gregorian_to_shamsi(value)
    return f"{year:04d}-{month:02d}"


def month_bounds(period):
    year, month = parse_shamsi_month(period)
    return (shamsi_to_gregorian(year, month, 1),
            shamsi_to_gregorian(year, month, days_in_month(year, month)))


def add_months(year, month, count):
    """Move by whole Solar Hijri months without assuming fixed days."""
    _integer(count, "Solar Hijri month count")
    days_in_month(year, month)
    absolute = year * 12 + month - 1 + count
    new_year, index = divmod(absolute, 12)
    days_in_month(new_year, index + 1)
    return new_year, index + 1


def following_month(period):
    year, month = parse_shamsi_month(period)
    year, month = add_months(year, month, 1)
    return f"{year:04d}-{month:02d}"


def semester_bounds(start_iso, months=2):
    """Fixed-class start, exact number of Solar Hijri months, inclusive end."""
    _integer(months, "Semester length")
    if not 1 <= months <= 24:
        raise ValueError("Semester length must be 1-24 Solar Hijri months")
    year, month, day = gregorian_to_shamsi(start_iso)
    next_y, next_m = add_months(year, month, months)
    end_boundary = shamsi_to_gregorian(
        next_y, next_m, min(day, days_in_month(next_y, next_m)))
    return date.fromisoformat(str(start_iso)), end_boundary - timedelta(days=1)


def monthly_due_dates(first_period, count, grace_days=0):
    """Due first of each Solar Hijri month plus Owner-configured grace days.

    Native payment allocation is separate. This creates ONLY date proposals,
    not invoices or future-cash receipts.
    """
    _integer(count, "Month count")
    _integer(grace_days, "Payment grace days")
    if not 1 <= count <= 24 or not 0 <= grace_days <= 31:
        raise ValueError("Month count must be 1-24 and grace days 0-31")
    year, month = parse_shamsi_month(first_period)
    result = []
    for offset in range(count):
        y, m = add_months(year, month, offset)
        result.append(shamsi_to_gregorian(y, m, 1) + timedelta(days=grace_days))
    return result


def payroll_priority_date(worked_period, preferred_day=15):
    """Priority payment date in the NEXT Solar Hijri month, not a cash posting."""
    _integer(preferred_day, "Preferred payroll day")
    if not 1 <= preferred_day <= 29:
        raise ValueError("Preferred payroll day must be 1-29")
    year, month = parse_shamsi_month(following_month(worked_period))
    return shamsi_to_gregorian(year, month, preferred_day)


def payroll_following_month_end(worked_period):
    return month_bounds(following_month(worked_period))[1]


def fiscal_year_bounds(year):
    _nowruz(year)
    if year >= MAX_YEAR:
        raise ValueError("Cannot compute unsupported following fiscal year")
    return _nowruz(year), _nowruz(year + 1) - timedelta(days=1)


def solar_month_label(period):
    year, month = parse_shamsi_month(period)
    return f"{MONTH_NAMES[month - 1]} {year}"
