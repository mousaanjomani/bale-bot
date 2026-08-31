"""Mobile number normalization to the canonical local form 09XXXXXXXXX."""

FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_phone(raw: str) -> str:
    """'+98 912-123 4567' / '00989121234567' / '۰۹۱۲...' -> '09121234567'."""
    s = str(raw or "").translate(FA_DIGITS)
    s = "".join(ch for ch in s if ch.isdigit() or ch == "+")
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("0098"):
        s = s[4:]
    if s.startswith("98") and len(s) >= 12:
        s = s[2:]
    if s and not s.startswith("0"):
        s = "0" + s
    return s
