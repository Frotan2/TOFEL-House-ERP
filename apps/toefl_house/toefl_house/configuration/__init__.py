"""Versioned TOEFL House configuration: foundation package.

This package __init__ is deliberately empty and frappe-free: the pure
``configuration.rules`` module must stay importable offline (unit tests,
desk stubs) without a bench. All frappe-side machinery lives in
``configuration.audit``.
"""
