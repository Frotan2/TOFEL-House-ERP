"""International contact handling for Afghan and worldwide online learners.

Telephone text is contact information, never evidence that two people are
identical. Only national Afghanistan mobile numbers have a default country
interpretation. Other countries require an explicit +country calling code.
"""
import re
import unicodedata


def normalize_contact_phone(value):
    """Return canonical typed phone text without formatting, or raise ValueError.

    An Afghan mobile has exactly ten national digits beginning 07; its E.164
    equivalent starts +937 and has 8 more digits. International contacts use
    explicit +CC and 7–15 digits in total; country allocations cannot be
    confirmed from digit length alone and should never infer residence.
    """
    if not isinstance(value, str):
        raise ValueError("Phone must be text")
    text = value.strip()
    if not text:
        return ""
    if len(text) > 32:
        raise ValueError("Phone must be at most 32 characters")
    try:
        digits = "".join(str(unicodedata.decimal(char)) if char.isdecimal()
                         else char for char in text)
    except (TypeError, ValueError):
        raise ValueError("Phone contains an invalid digit") from None
    if not re.fullmatch(r"\+?[0-9 ()-]+", digits):
        raise ValueError("Phone may contain only digits, spaces, +, - and parentheses")
    clean = re.sub(r"[ ()-]", "", digits)
    if re.fullmatch(r"07[0-9]{8}", clean):
        return clean
    if clean.startswith("07"):
        raise ValueError("Afghan mobile numbers must have exactly 10 digits, starting 07")
    if re.fullmatch(r"\+[1-9][0-9]{6,14}", clean):
        if clean.startswith("+93") and not re.fullmatch(r"\+937[0-9]{8}", clean):
            raise ValueError("Afghan mobile numbers must use 07xxxxxxxx or +937xxxxxxxx")
        return clean
    if clean.startswith("+"):
        raise ValueError("International numbers must start +country-code and contain 7–15 digits")
    raise ValueError("Use 07xxxxxxxx for Afghanistan or +country-code for other countries")


def afghan_phone_variants(contact):
    """Return Afghan national first and +93 second, otherwise exact value."""
    if re.fullmatch(r"07[0-9]{8}", contact or ""):
        return (contact, "+93" + contact[1:])
    if re.fullmatch(r"\+937[0-9]{8}", contact or ""):
        return ("0" + contact[3:], contact)
    return (contact,)
