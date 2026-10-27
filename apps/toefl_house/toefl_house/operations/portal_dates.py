"""Explicit Afghan Solar Hijri display dates without changing native dates.

These are civil-date labels, not timezone conversions; a site must still be
configured for Asia/Kabul when choosing the current operating date.
"""


def with_solar_date(rows, source_field, display_field):
    """Copy rows and add a labeled display date, or None outside support.

    The same bounded, owner-approved conversion governs academic periods.
    Native ISO dates remain untouched and are displayed alongside this value.
    """
    from toefl_house.finance.shamsi import MONTH_NAMES, gregorian_to_shamsi

    projected = []
    for row in rows:
        item = dict(row)
        value = item.get(source_field)
        try:
            year, month, day = gregorian_to_shamsi(value)
            item[display_field] = f"{day:02d} {MONTH_NAMES[month - 1]} {year}"
        except (TypeError, ValueError):
            item[display_field] = None
        projected.append(item)
    return projected
