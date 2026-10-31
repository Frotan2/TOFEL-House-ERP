# OAuth device-code grant boundary — 27 October 2026

Foundation run 40519483121 on 3334faf65f3e failed closed for the newly indexed
[GHSA-3jp2-3mrg-2vxc](https://github.com/advisories/GHSA-3jp2-3mrg-2vxc).
The advisory concerns missing device-code validation in OAuthLib 3.3.1.

Pinned Frappe 988e54f3c4c291e2077a83809663f123731abe76 imports the OpenID
preconfigured Server in integrations/oauth2.py. That server does register the
device-code grant; absence of a user-facing device screen is not sufficient
evidence of safety. However frappe/oauth.py:182–185 implements
OAuthWebRequestValidator.validate_grant_type with an explicit allowlist:
authorization_code, refresh_token, password. Device-code is excluded.

On the preserved Windows runtime, a probe instantiated the actual OAuthLib
OpenID Server with the actual Frappe validator. Only client authentication was
replaced with successful synthetic authentication to exercise the grant gate
without a real client or credentials. The real grant validator remained
unchanged. Both a missing device code and a bogus device code returned 400
unauthorized_client. Neither response contained a token; a persistence trap was
never reached. No database connection or operational write was needed.

tools/native/security_acceptance.py repeats this behavior in hosted acceptance.
This finding is NOT_REACHABLE through the pinned token endpoint. Adding device
workflow support or changing the grant allowlist requires a new review. This
does not assert that OAuthLib 3.3.1 itself is patched or close unrelated release
gates. The immutable earlier advisory register is unchanged.
