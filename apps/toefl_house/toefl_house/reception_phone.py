"""Unambiguous Afghan mobile contact matching for Reception.

These variants support searching/deduplicating a contact, not identifying a
person. Shared family numbers remain separate visitor identities. Preserve
the user's actual entered national/international number for display and audit.
"""
import re


def afghan_phone_variants(contact):
    """Return the national format first for a valid Afghan mobile number."""
    if re.fullmatch(r"07[0-9]{8}", contact or ""):
        return (contact, "+93" + contact[1:])
    if re.fullmatch(r"\+937[0-9]{8}", contact or ""):
        return ("0" + contact[3:], contact)
    return (contact,)
