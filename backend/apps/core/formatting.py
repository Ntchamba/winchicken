"""French number formatting for text the backend writes for people to read (alert messages,
SMS). The UI is French everywhere; "9.5kg" in an alert next to "1,6-2,2" was not.
"""


def fr_number(value, max_decimals=2):
    """`9.5` -> "9,5", `10.0` -> "10", `1234.5` -> "1 234,5": decimal comma, no trailing zeros,
    a space between thousands (the same grouping utils/money.js uses for FCFA)."""
    text = f"{float(value):,.{max_decimals}f}"
    if max_decimals:
        text = text.rstrip('0').rstrip('.')
    return text.replace(',', ' ').replace('.', ',')
