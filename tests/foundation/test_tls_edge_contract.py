"""Static and behavioural contract for the operational TLS/edge boundary (P5).

The recovery and custody work proved a site comes back and its keys come back.
What neither exercised is the boundary a real deployment is reached through: a
front proxy that terminates TLS, refuses plaintext, pins protocol versions, and
still serves private files only through the application's own permission check.

This contract keeps that honest without touching a network:

* the certificate commands are the ones OpenSSL actually accepts, and the
  hostname lands in ``subjectAltName`` - modern clients match the SAN and ignore
  the CN, so a CN-only certificate would make the hostname control pass for the
  wrong reason;
* the parsers read real ``openssl s_client`` text. OpenSSL 3 prints a TLS 1.2
  session with an ``SSL-Session:`` block and a TLS 1.3 session without one, so a
  parser written against the indented form reports "TLS 1.3 refused" on a
  perfectly healthy listener. Every fixture below is verbatim output captured
  from OpenSSL 3.0.20 against a live TLS server;
* ``s_client`` does not verify the hostname unless ``-verify_hostname`` is passed,
  so the command builder must pass it;
* ``-CAfile /dev/null`` is not "no trust anchor" - OpenSSL fails while loading the
  store and never attempts a handshake. The real control is an unrelated CA,
  which yields a genuine chain-validation failure (return code 21);
* a refused handshake still prints ``Verify return code: 0 (ok)`` because no
  certificate was exchanged, so verification success is only reported once a
  cipher was agreed;
* a refusal caused by the client's own OpenSSL policy is separated from one caused
  by the server, because only the second is evidence about the boundary;
* the tailnet verdict cannot be upgraded: no auth key, no node, no ACL. It reports
  the binding shape and classifies the rest ENVIRONMENT-BLOCKED;
* the rollback verdict requires a matching version *and* a byte-identical artifact
  digest, so a rollback that merely claims success does not pass.

Boundary with the existing coverage: ``test_independent_recovery_contract.py`` and
``runtime_independent_usability.py`` exercise the plaintext proxy and the
``X-Accel-Redirect`` privacy boundary. This file adds the TLS edge on top of the
same pinned nginx template. Neither upgrades a release gate; the PASS comes from
the hosted operational-boundary run, never from this file.
"""
import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import tls_edge as edge  # noqa: E402


# Verbatim output captured from OpenSSL 3.0.20 against a live TLS listener whose
# certificate was issued by a private CA for ``edge.foundation.internal``. These
# are parser fixtures, not execution evidence: the evidence comes from the hosted
# run that performs the same handshakes against a real nginx listener.
TLS12_WITH_CA = """
 0 s:CN = edge.foundation.internal
   i:CN = Test CA
SSL handshake has read 1505 bytes and written 314 bytes
Verification: OK
New, TLSv1.2, Cipher is ECDHE-RSA-AES256-GCM-SHA384
SSL-Session:
    Protocol  : TLSv1.2
    Cipher    : ECDHE-RSA-AES256-GCM-SHA384
    Verify return code: 0 (ok)
"""
TLS13_WITH_CA = """
 0 s:CN = edge.foundation.internal
   i:CN = Test CA
SSL handshake has read 1420 bytes and written 338 bytes
Verification: OK
New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
Verify return code: 0 (ok)
"""
TLS11_REFUSED = """
SSL handshake has read 7 bytes and written 137 bytes
Verification: OK
New, (NONE), Cipher is (NONE)
SSL-Session:
    Protocol  : TLSv1.1
    Cipher    : 0000
    Verify return code: 0 (ok)
808BDD801D7F0000:error:0A00042E:SSL routines:ssl3_read_bytes:tlsv1 alert protocol version:../ssl/record/rec_layer_s3.c:1601:SSL alert number 70
"""
TLS10_REFUSED = """
SSL handshake has read 7 bytes and written 137 bytes
Verification: OK
New, (NONE), Cipher is (NONE)
SSL-Session:
    Protocol  : TLSv1
    Cipher    : 0000
    Verify return code: 0 (ok)
802B44601E7F0000:error:0A00042E:SSL routines:ssl3_read_bytes:tlsv1 alert protocol version:../ssl/record/rec_layer_s3.c:1601:SSL alert number 70
"""
UNRELATED_CA = """
 0 s:CN = edge.foundation.internal
   i:CN = Test CA
SSL handshake has read 1420 bytes and written 410 bytes
Verification error: unable to verify the first certificate
New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
Verify return code: 21 (unable to verify the first certificate)
verify error:num=20:unable to get local issuer certificate
verify error:num=21:unable to verify the first certificate
"""
WRONG_HOSTNAME = """
 0 s:CN = edge.foundation.internal
   i:CN = Test CA
SSL handshake has read 1420 bytes and written 410 bytes
Verification error: hostname mismatch
New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
Verify return code: 62 (hostname mismatch)
verify error:num=62:hostname mismatch
"""
CERT_TEXT = """
        Signature Algorithm: sha256WithRSAEncryption
            Not After : Sep 19 07:39:29 2026 GMT
        Subject: CN = edge.foundation.internal
                CA:FALSE
            X509v3 Subject Alternative Name: 
                DNS:edge.foundation.internal
    Signature Algorithm: sha256WithRSAEncryption
"""


class CommandBuilders(unittest.TestCase):
    """The commands must be ones OpenSSL 3 accepts, with the hostname in the SAN."""

    def test_ca_commands_are_two_real_steps(self):
        commands = edge.ca_commands("/lab", days=2)
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][0:3], ["openssl", "genpkey", "-algorithm"])
        self.assertEqual(commands[1][0:3], ["openssl", "req", "-x509"])
        self.assertIn("CA:TRUE", " ".join(commands[1]))

    def test_leaf_certificate_puts_the_hostname_in_the_san(self):
        commands, meta = edge.server_cert_commands("/lab", host="edge.foundation.internal")
        joined = " ".join(" ".join(command) for command in commands)
        self.assertIn("x509", joined)
        self.assertIn("-CAcreateserial", joined)
        self.assertEqual(meta["san"], "DNS:edge.foundation.internal")
        self.assertIn("subjectAltName=DNS:edge.foundation.internal",
                      meta["extensions_stdin"])
        # A CN-only certificate would make the hostname control meaningless.
        self.assertIn("extendedKeyUsage=serverAuth", meta["extensions_stdin"])

    def test_s_client_verifies_the_hostname_explicitly(self):
        command = edge.s_client_command(
            8443, cafile="/lab/ca.pem", servername="edge.foundation.internal",
            verify_hostname="edge.foundation.internal")
        self.assertIn("-verify_hostname", command)
        self.assertEqual(command[command.index("-verify_hostname") + 1],
                         "edge.foundation.internal")

    def test_s_client_never_uses_dev_null_as_a_trust_store(self):
        # /dev/null makes OpenSSL fail while loading the store and proves nothing.
        command = edge.s_client_command(8443, cafile=None, empty_store="/lab/unrelated.pem")
        self.assertNotIn("/dev/null", command)
        self.assertIn("/lab/unrelated.pem", command)

    def test_protocol_flags_are_the_ones_openssl_accepts(self):
        self.assertEqual(edge.protocol_flag("TLSv1.3"), "-tls1_3")
        self.assertEqual(edge.protocol_flag("TLSv1.1"), "-tls1_1")
        self.assertEqual(edge.protocol_flag("TLSv1"), "-tls1")
        with self.assertRaises(KeyError):
            edge.protocol_flag("TLSv4")


class NginxPolicy(unittest.TestCase):
    """The TLS listener keeps the pinned bench template and adds the boundary."""

    def setUp(self):
        self.conf = edge.nginx_tls_conf(
            lab="/lab", bench_dir="/bench", site="front", http_port=8080,
            https_port=8443, backend_port="127.0.0.1:8000",
            certificate="/lab/server.pem", key="/lab/server.key")

    def test_terminates_tls_with_the_issued_certificate(self):
        self.assertIn("listen 127.0.0.1:8443 ssl;", self.conf)
        self.assertIn("ssl_certificate /lab/server.pem;", self.conf)
        self.assertIn("ssl_certificate_key /lab/server.key;", self.conf)

    def test_plaintext_listener_only_redirects(self):
        # One boundary, not two: plaintext answers with a redirect and nothing else.
        self.assertIn("listen 127.0.0.1:8080;", self.conf)
        # The port is rendered by Python, not referenced as $https_port: nginx has no
        # such variable and would fail `nginx -t` with "unknown variable".
        self.assertIn("return 301 https://edge.foundation.internal:8443$request_uri;",
                      self.conf)
        self.assertNotIn("$https_port", self.conf)
        # The pinned template hardcodes 443; binding it needs root, so the probe
        # uses an unprivileged port and the deviation is recorded in the report.
        self.assertNotIn("listen 80;", self.conf)
        self.assertNotIn("listen 443", self.conf)

    def test_hsts_is_the_value_the_pinned_template_declares(self):
        # 63072000 (two years) with includeSubDomains and preload, verbatim from
        # frappe/bench config/templates/nginx.conf - not a value invented here.
        self.assertEqual(edge.HSTS_MAX_AGE, 63072000)
        self.assertIn("Strict-Transport-Security", self.conf)
        self.assertIn(f'"max-age={edge.HSTS_MAX_AGE}; includeSubDomains; preload"', self.conf)

    def test_protocol_policy_is_declared_at_the_listener(self):
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3;", self.conf)
        self.assertNotIn("TLSv1.1", self.conf.replace("ssl_protocols TLSv1.2 TLSv1.3;", ""))
        self.assertNotIn("SSLv3", self.conf)

    def test_the_pinned_templates_cipher_and_session_settings_are_used(self):
        for directive in ("ssl_ciphers EECDH+AESGCM:EDH+AESGCM;",
                          "ssl_ecdh_curve secp384r1;",
                          "ssl_session_tickets off;",
                          "ssl_session_timeout 5m;",
                          "ssl_prefer_server_ciphers on;"):
            self.assertIn(directive, self.conf)

    def test_the_pinned_templates_security_headers_are_present(self):
        for header in ('add_header X-Frame-Options "SAMEORIGIN";',
                       "add_header X-Content-Type-Options nosniff;",
                       'add_header X-XSS-Protection "1; mode=block";',
                       'add_header Referrer-Policy "same-origin, '
                       'strict-origin-when-cross-origin";'):
            self.assertIn(header, self.conf)

    def test_the_backend_is_reached_through_a_named_upstream(self):
        # As the pinned template does, rather than proxying to a bare port.
        self.assertIn("upstream foundation-frappe {", self.conf)
        self.assertIn("server 127.0.0.1:8000 fail_timeout=0;", self.conf)
        self.assertIn("proxy_pass http://foundation-frappe;", self.conf)

    def test_private_files_still_go_through_the_internal_location(self):
        # The P3 fix must survive the move to TLS: X-Accel-Redirect needs an
        # ``internal`` location, without which the request 500s.
        self.assertIn("location ~ ^/protected/(.*) {", self.conf)
        self.assertIn("internal;", self.conf)
        self.assertIn("proxy_set_header X-Use-X-Accel-Redirect True;", self.conf)
        self.assertIn("location @webserver {", self.conf)

    def test_host_allowlist_is_not_client_supplied(self):
        self.assertIn("map $host $foundation_site", self.conf)
        self.assertIn("if ($foundation_site = '') { return 444; }", self.conf)
        self.assertIn("proxy_set_header X-Frappe-Site-Name $foundation_site;", self.conf)

    def test_binding_address_is_parameterised(self):
        bound = edge.nginx_tls_conf(
            lab="/lab", bench_dir="/bench", site="front", http_port=8080,
            https_port=8443, backend_port="127.0.0.1:8000", certificate="/c.pem",
            key="/k.pem", bind="10.0.0.5")
        self.assertIn("listen 10.0.0.5:8443 ssl;", bound)
        self.assertNotIn("0.0.0.0", bound)

    def test_forwarded_proto_is_the_pinned_templates_scheme_variable(self):
        # Gunicorn's default forwarded_allow_ips is 127.0.0.1,::1 and its default
        # secure_scheme_headers maps X-FORWARDED-PROTO=https, so this is what makes
        # frappe.auth set the Secure flag on the session cookie. Hardcoding "https"
        # would work too, but $scheme is what the template sends.
        self.assertIn("proxy_set_header X-Forwarded-Proto $scheme;", self.conf)
        self.assertIn("proxy_set_header Host $host;", self.conf)

    def test_the_plaintext_listener_never_proxies(self):
        # The redirect-only server block must not contain a proxy_pass: plaintext
        # has to be refused structurally, not by a rule that could be bypassed.
        plaintext_block = self.conf.split("server {")[1]
        self.assertIn("return 301", plaintext_block)
        self.assertNotIn("proxy_pass", plaintext_block)
        self.assertNotIn("try_files", plaintext_block)


class SClientParser(unittest.TestCase):
    """Parsers against real OpenSSL 3 output, including the TLS 1.3 shape."""

    def test_tls12_reads_protocol_cipher_and_verification(self):
        parsed = edge.parse_s_client(TLS12_WITH_CA)
        self.assertEqual(parsed["protocol"], "TLSv1.2")
        self.assertTrue(parsed["protocol_found"])
        self.assertEqual(parsed["cipher"], "ECDHE-RSA-AES256-GCM-SHA384")
        self.assertTrue(parsed["cipher_found"])
        self.assertEqual(parsed["verify_return_code"], 0)
        self.assertTrue(parsed["verification_succeeded"])
        self.assertTrue(parsed["handshake_completed"])
        self.assertFalse(parsed["refused"])
        self.assertIn("edge.foundation.internal", parsed["subject"])
        self.assertEqual(parsed["protocol_source"], "New/Cipher line")

    def test_tls13_is_parsed_even_without_an_ssl_session_block(self):
        # OpenSSL 3 omits the SSL-Session block for TLS 1.3. A parser written
        # against the indented form would report this healthy session as refused.
        self.assertNotIn("SSL-Session:", TLS13_WITH_CA)
        parsed = edge.parse_s_client(TLS13_WITH_CA)
        self.assertEqual(parsed["protocol"], "TLSv1.3")
        self.assertEqual(parsed["cipher"], "TLS_AES_256_GCM_SHA384")
        self.assertTrue(parsed["cipher_found"])
        self.assertTrue(parsed["handshake_completed"])
        self.assertFalse(parsed["refused"])

    def test_a_refused_handshake_is_not_reported_as_verified(self):
        for fixture, offered in ((TLS10_REFUSED, "TLSv1"), (TLS11_REFUSED, "TLSv1.1")):
            parsed = edge.parse_s_client(fixture)
            self.assertIn("Verify return code: 0 (ok)", fixture,
                          "the fixture must keep the misleading line the parser must not trust")
            self.assertIsNone(parsed["verification_succeeded"])
            self.assertFalse(parsed["cipher_found"])
            self.assertFalse(parsed["handshake_completed"])
            self.assertTrue(parsed["refused"])
            self.assertEqual(parsed["protocol_attempted"], offered)
            self.assertIsNone(parsed["protocol"])

    def test_server_side_refusal_is_distinguished_from_client_side(self):
        parsed = edge.parse_s_client(TLS11_REFUSED)
        self.assertTrue(parsed["refusal_attributable_to_server"])
        self.assertIn("SERVER-SIDE", parsed["refusal_reason"])
        client_only = edge.parse_s_client(
            "error:0A00010B:SSL routines::wrong version number\n"
            "no protocols available")
        self.assertFalse(client_only["refusal_attributable_to_server"])

    def test_a_store_that_fails_to_load_is_not_evidence_about_the_server(self):
        parsed = edge.parse_s_client(
            "error:05800088:x509 certificate routines:X509_load_cert_crl_file_ex:"
            "no certificate or crl found")
        self.assertIn("NO HANDSHAKE ATTEMPTED", parsed["refusal_reason"])
        self.assertFalse(parsed["refusal_attributable_to_server"])

    def test_empty_output_is_reported_as_no_evidence(self):
        parsed = edge.parse_s_client("")
        self.assertFalse(parsed["protocol_found"])
        self.assertFalse(parsed["cipher_found"])
        self.assertIsNone(parsed["verification_succeeded"])
        self.assertEqual(parsed["output_bytes"], 0)


class CertificateTextParser(unittest.TestCase):
    def test_reads_the_san_from_the_certificate_itself(self):
        parsed = edge.parse_certificate_text(CERT_TEXT)
        self.assertEqual(parsed["common_name"], "edge.foundation.internal")
        self.assertEqual(parsed["subject_alt_names"], ["DNS:edge.foundation.internal"])
        self.assertTrue(parsed["subject_alt_names_found"])
        self.assertFalse(parsed["is_ca"])
        self.assertEqual(parsed["signature_algorithm"], "sha256WithRSAEncryption")
        self.assertIsNotNone(parsed["not_after"])

    def test_a_ca_certificate_is_recognised_as_one(self):
        parsed = edge.parse_certificate_text("Subject: CN = Test CA\n    CA:TRUE\n")
        self.assertTrue(parsed["is_ca"])


class HstsParser(unittest.TestCase):
    def test_parses_the_directive_the_config_declares(self):
        parsed = edge.parse_hsts(f"max-age={edge.HSTS_MAX_AGE}; includeSubDomains")
        self.assertTrue(parsed["present"])
        self.assertTrue(parsed["well_formed"])
        self.assertEqual(parsed["max_age"], edge.HSTS_MAX_AGE)
        self.assertTrue(parsed["include_subdomains"])
        self.assertFalse(parsed["preload"])

    def test_a_missing_or_malformed_header_is_not_well_formed(self):
        self.assertFalse(edge.parse_hsts(None)["present"])
        self.assertFalse(edge.parse_hsts("")["well_formed"])
        self.assertFalse(edge.parse_hsts("includeSubDomains")["well_formed"])
        self.assertIsNone(edge.parse_hsts("max-age=abc")["max_age"])


class ProtocolPolicyVerdict(unittest.TestCase):
    def observed(self):
        return {
            "TLSv1.2": edge.parse_s_client(TLS12_WITH_CA),
            "TLSv1.3": edge.parse_s_client(TLS13_WITH_CA),
            "TLSv1": edge.parse_s_client(TLS10_REFUSED),
            "TLSv1.1": edge.parse_s_client(TLS11_REFUSED),
        }

    def test_real_observations_satisfy_the_policy(self):
        verdict = edge.protocol_policy_verdict(self.observed())
        self.assertEqual(verdict["verdict"], "POLICY ENFORCED")
        self.assertEqual(verdict["policy_violations"], [])
        self.assertEqual(verdict["protocols_with_no_evidence"], [])
        self.assertEqual(verdict["per_protocol"]["TLSv1.3"]["outcome"], "ACCEPTED")
        self.assertEqual(verdict["per_protocol"]["TLSv1.1"]["outcome"], "REFUSED")

    def test_an_allowed_protocol_being_refused_fails_closed(self):
        observed = self.observed()
        observed["TLSv1.3"] = edge.parse_s_client(TLS11_REFUSED)
        verdict = edge.protocol_policy_verdict(observed)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("TLSv1.3", verdict["policy_violations"])

    def test_a_refused_protocol_being_accepted_fails_closed(self):
        observed = self.observed()
        observed["TLSv1.1"] = edge.parse_s_client(TLS12_WITH_CA)
        verdict = edge.protocol_policy_verdict(observed)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("TLSv1.1", verdict["policy_violations"])

    def test_a_client_side_refusal_is_not_server_evidence(self):
        observed = self.observed()
        observed["TLSv1.1"] = edge.parse_s_client("no protocols available")
        verdict = edge.protocol_policy_verdict(observed)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("TLSv1.1", verdict["protocols_with_no_evidence"])

    def test_unparseable_output_never_passes(self):
        verdict = edge.protocol_policy_verdict({"TLSv1.2": edge.parse_s_client("")})
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(verdict["protocols_with_no_evidence"], ["TLSv1.2"])


class TrustVerdict(unittest.TestCase):
    def test_real_observations_prove_verification_is_enforced(self):
        verdict = edge.trust_verdict(
            edge.parse_s_client(TLS12_WITH_CA),
            edge.parse_s_client(UNRELATED_CA),
            edge.parse_s_client(WRONG_HOSTNAME))
        self.assertEqual(verdict["verdict"], "VERIFICATION ENFORCED")
        self.assertTrue(verdict["verification_enforced"])
        self.assertEqual(verdict["verify_return_code_with_ca"], 0)
        self.assertEqual(verdict["verify_return_code_without_ca"], 21)
        self.assertEqual(verdict["wrong_name_verify_return_code"], 62)
        self.assertTrue(verdict["hostname_binding_enforced"])
        self.assertIn("private test CA", verdict["trust_anchor_note"])

    def test_trusting_an_unrelated_ca_fails_closed(self):
        verdict = edge.trust_verdict(
            edge.parse_s_client(UNRELATED_CA),
            edge.parse_s_client(UNRELATED_CA),
            edge.parse_s_client(WRONG_HOSTNAME))
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertFalse(verdict["verification_enforced"])

    def test_a_wrong_name_being_accepted_fails_closed(self):
        verdict = edge.trust_verdict(
            edge.parse_s_client(TLS12_WITH_CA),
            edge.parse_s_client(UNRELATED_CA),
            edge.parse_s_client(TLS12_WITH_CA))
        self.assertFalse(verdict["hostname_binding_enforced"])
        self.assertEqual(verdict["verdict"], "NOT PROVEN")

    def test_the_hostname_control_is_required_not_optional(self):
        # A chain-only check cannot prove hostname binding.
        verdict = edge.trust_verdict(edge.parse_s_client(TLS12_WITH_CA),
                                     edge.parse_s_client(UNRELATED_CA))
        self.assertIsNone(verdict["hostname_binding_enforced"])
        self.assertTrue(verdict["verification_enforced"])
        self.assertNotIn("hostname", verdict["verdict"].lower())


class TailnetBoundaryVerdict(unittest.TestCase):
    """No auth key exists, so this must stay ENVIRONMENT-BLOCKED."""

    def test_without_an_auth_key_it_is_blocked_not_proven(self):
        verdict = edge.tailscale_boundary_verdict(["127.0.0.1:8443"])
        self.assertEqual(verdict["status"], "ENVIRONMENT-BLOCKED")
        self.assertFalse(verdict["bound_to_every_interface"])
        self.assertTrue(verdict["not_simulated"])
        self.assertIn("no tailnet was joined", verdict["what_is_not_proven"])
        self.assertEqual(len(verdict["owner_inputs_required"]), 3)

    def test_a_wildcard_binding_is_reported_as_not_tailnet_only(self):
        # The host part decides the binding, with or without a port.
        for addresses in (["0.0.0.0:8443"], ["0.0.0.0"], ["*"], ["[::]:8443"], ["::"]):
            verdict = edge.tailscale_boundary_verdict(addresses)
            self.assertTrue(verdict["bound_to_every_interface"], addresses)
            self.assertEqual(verdict["wildcard_addresses"], addresses, addresses)
            self.assertIn("NOT tailnet-only", verdict["what_is_proven"])

    def test_an_explicit_binding_is_never_reported_as_wildcard(self):
        for addresses in (["127.0.0.1:8443"], ["10.0.0.5:443"],
                          ["100.64.0.7:443", "127.0.0.1:8443"]):
            verdict = edge.tailscale_boundary_verdict(addresses)
            self.assertFalse(verdict["bound_to_every_interface"], addresses)
            self.assertEqual(verdict["wildcard_addresses"], [], addresses)

    def test_an_auth_key_changes_the_status_and_nothing_else(self):
        blocked = edge.tailscale_boundary_verdict(["127.0.0.1:8443"])
        executed = edge.tailscale_boundary_verdict(["127.0.0.1:8443"], auth_key_available=True,
                                                   tailscale_binary="/usr/bin/tailscale")
        self.assertEqual(executed["status"], "EXECUTED")
        self.assertEqual(executed["what_is_not_proven"], blocked["what_is_not_proven"])


class KernelListenerDecoder(unittest.TestCase):
    """Binding evidence comes from /proc, which reports what the kernel bound.

    Fixtures are verbatim rows from a real Linux /proc/net/tcp and /proc/net/tcp6,
    including one established (non-listening) row that must be ignored and one
    genuine wildcard listener.
    """

    PROC_TCP = """  sl  local_address rem_address   st tx_queue rx_queue
   0: 0100007F:4844 00000000:0000 0A 00000000:00000000 00:00000000
   1: 1500FEA9:4844 00000000:0000 0A 00000000:00000000 00:00000000
   2: 00000000:006F 00000000:0000 0A 00000000:00000000 00:00000000
   3: 0100007F:1F90 0100007F:9C40 01 00000000:00000000 00:00000000
"""
    PROC_TCP6 = """  sl  local_address                         remote_address                        st
   0: 00000000000000000000000000000000:C33F 00000000000000000000000000000000:0000 0A
   1: 00000000000000000000000001000000:1F91 00000000000000000000000000000000:0000 0A
"""

    def setUp(self):
        self.rows = (edge.decode_proc_net_listeners(self.PROC_TCP)
                     + edge.decode_proc_net_listeners(self.PROC_TCP6))

    def test_kernel_byte_order_is_reversed_into_dotted_form(self):
        decoded = {(row["address"], row["port"]) for row in self.rows}
        self.assertIn(("127.0.0.1", 18500), decoded)
        self.assertIn(("169.254.0.21", 18500), decoded)
        self.assertIn(("0.0.0.0", 111), decoded)

    def test_ipv6_wildcard_and_loopback_are_decoded(self):
        decoded = {(row["address"], row["port"]) for row in self.rows}
        self.assertIn(("::", 49983), decoded)
        self.assertIn(("::1", 8081), decoded)

    def test_only_listening_rows_are_returned(self):
        # Row 3 is an established connection (state 01), not a listener.
        self.assertEqual(len(edge.decode_proc_net_listeners(self.PROC_TCP)), 3)
        self.assertTrue(all(row["raw"] != "0100007F:1F90" for row in self.rows))

    def test_a_wildcard_binding_is_identified(self):
        shape = edge.binding_shape(self.rows, [111, 49983])
        self.assertTrue(shape["111"]["bound_to_every_interface"])
        self.assertTrue(shape["49983"]["bound_to_every_interface"])

    def test_an_explicit_binding_is_not_wildcard(self):
        shape = edge.binding_shape(self.rows, [18500])
        self.assertTrue(shape["18500"]["listening"])
        self.assertFalse(shape["18500"]["bound_to_every_interface"])
        self.assertEqual(sorted(shape["18500"]["addresses"]),
                         ["127.0.0.1", "169.254.0.21"])

    def test_a_port_that_never_bound_is_reported_absent_not_skipped(self):
        shape = edge.binding_shape(self.rows, [9999])
        self.assertFalse(shape["9999"]["listening"])
        self.assertEqual(shape["9999"]["addresses"], [])
        self.assertIsNone(shape["9999"]["bound_to_every_interface"])

    def test_unparseable_input_yields_no_listeners(self):
        self.assertEqual(edge.decode_proc_net_listeners(""), [])
        self.assertEqual(edge.decode_proc_net_listeners(None), [])
        self.assertEqual(edge.decode_proc_net_listeners("garbage without colons"), [])


class RollbackVerdict(unittest.TestCase):
    def test_matching_version_and_digest_is_proven(self):
        verdict = edge.rollback_verdict("frappe 16.33.1 HEAD", "frappe 16.33.1 HEAD",
                                        "abc123", "abc123")
        self.assertEqual(verdict["verdict"], "ROLLBACK RESTORED THE PRIOR VERSIONED ARTIFACT")
        self.assertTrue(verdict["version_restored"])
        self.assertTrue(verdict["artifact_is_the_same_bytes"])

    def test_a_version_mismatch_fails_closed(self):
        verdict = edge.rollback_verdict("frappe 16.33.1 HEAD", "frappe 16.34.0 HEAD",
                                        "abc123", "abc123")
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(verdict["reason"], "version mismatch")

    def test_a_digest_mismatch_fails_closed(self):
        verdict = edge.rollback_verdict("frappe 16.33.1 HEAD", "frappe 16.33.1 HEAD",
                                        "abc123", "def456")
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(verdict["reason"], "artifact digest mismatch")

    def test_empty_observations_fail_closed(self):
        self.assertEqual(edge.rollback_verdict("", "", "", "")["verdict"], "NOT PROVEN")
        self.assertEqual(edge.rollback_verdict("v1", "v1", "", "")["verdict"], "NOT PROVEN")


class LegacyProtocolObservabilityTests(unittest.TestCase):
    """A legacy-protocol refusal must be attributable to the listener, not the client.

    Run 35214660151 (this branch) and its historical-provenance predecessor run
    35197870620 on the prior session branch both failed the TLS edge at exactly one
    check with
    ``"reason": "no parseable evidence for: TLSv1, TLSv1.1"``: the distribution
    crypto policy stops ``openssl s_client`` from even offering TLS 1.0, so the
    refusal it reported was the client's own and said nothing about the listener.
    The probe correctly refused to call that POLICY ENFORCED - but the claim stayed
    unproven and the gate stayed red. These tests pin the policy-independent
    instrument that resolves it, exercised against real TLS servers on loopback.
    """

    @classmethod
    def setUpClass(cls):
        import ssl
        cls.ssl = ssl
        cls.edge = edge
        # Only the module-level helpers are needed; nothing here starts a check.
        source = (ROOT / "tools/foundation/runtime_tls_edge_checks.py").read_text(encoding="utf-8")
        namespace = {"edge": edge, "socket": socket, "struct": struct, "os": os}
        exec(compile(source[source.index("def legacy_protocol_outcome("):
                            source.index("def pem_to_der_sha256(")], "probe", "exec"), namespace)
        # staticmethod: a bare function assigned to a class attribute would be
        # bound, silently shifting every argument one place to the right.
        cls.probe = staticmethod(namespace["legacy_protocol_outcome"])
        cls.certificate = cls._write_certificate()

    @staticmethod
    def _write_certificate():
        directory = Path(tempfile.mkdtemp(prefix="toefl-house-tls-"))
        certificate = directory / "cert.pem"
        key = directory / "key.pem"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(key),
             "-out", str(certificate), "-days", "1", "-nodes", "-subj", "/CN=probe.test",
             "-addext", "subjectAltName=DNS:probe.test"],
            capture_output=True, check=True, timeout=120)
        return certificate

    def _serve(self, minimum_version, ciphers=None):
        # Serving TLS 1.0 here is the point of the negative control, so the
        # deprecation warning is expected rather than a signal to change anything.
        warnings.simplefilter("ignore", DeprecationWarning)
        context = self.ssl.SSLContext(self.ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self.certificate),
                                str(self.certificate.parent / "key.pem"))
        context.minimum_version = minimum_version
        if ciphers:
            context.set_ciphers(ciphers)
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen(8)

        def accept():
            for _ in range(6):
                try:
                    connection, _ = server.accept()
                except OSError:
                    return
                try:
                    with context.wrap_socket(connection, server_side=True) as tls:
                        tls.recv(16)
                except Exception:  # noqa: BLE001 - a refused handshake is the point
                    try:
                        connection.close()
                    except OSError:
                        pass

        threading.Thread(target=accept, daemon=True).start()
        time.sleep(0.5)
        self.addCleanup(server.close)
        return port

    def test_a_listener_that_refuses_legacy_versions_is_observed_refusing(self):
        port = self._serve(self.ssl.TLSVersion.TLSv1_2)
        for protocol, expected_alert in (("TLSv1", "protocol_version"),
                                         ("TLSv1.1", "protocol_version")):
            with self.subTest(protocol=protocol):
                observation = self.probe("127.0.0.1", port, protocol)
                self.assertEqual(observation["outcome"], "ALERT")
                self.assertEqual(observation["alert_description"], expected_alert)
                self.assertTrue(observation["refusal_attributable_to_server"],
                                "the refusal was not attributed to the listener")

    def test_a_listener_that_accepts_legacy_versions_is_observed_accepting(self):
        """The negative control: an accepting listener must not read as refused."""
        port = self._serve(self.ssl.TLSVersion.TLSv1, ciphers="DEFAULT@SECLEVEL=0")
        observation = self.probe("127.0.0.1", port, "TLSv1")
        self.assertEqual(observation["outcome"], "SERVER_HELLO")
        self.assertEqual(observation["negotiated_version"], "0x030x01")
        self.assertFalse(observation["refusal_attributable_to_server"])

    def test_an_unreachable_listener_is_no_evidence_and_never_a_refusal(self):
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
        closed.close()
        observation = self.probe("127.0.0.1", port, "TLSv1")
        self.assertEqual(observation["outcome"], "NO EVIDENCE")
        self.assertFalse(observation["refusal_attributable_to_server"])

    def test_the_recorded_runner_state_resolves_to_policy_enforced(self):
        """Replay the exact outcomes run 35214660151 published."""
        attempts = {
            "TLSv1.2": {"protocol_found": True, "cipher_found": True,
                        "handshake_completed": True, "verification_succeeded": True,
                        "protocol": "TLSv1.2", "cipher": "ECDHE-RSA-AES256-GCM-SHA384"},
            "TLSv1.3": {"protocol_found": True, "cipher_found": True,
                        "handshake_completed": True, "verification_succeeded": True,
                        "protocol": "TLSv1.3", "cipher": "TLS_AES_256_GCM_SHA384"},
            "SSLv3": {"protocol_found": False, "refused": True, "handshake_completed": False,
                      "refusal_attributable_to_server": True, "refusal_reason": "alert"},
            "TLSv1": {"protocol_found": False, "refused": True, "handshake_completed": False,
                      "refusal_attributable_to_server": False,
                      "refusal_reason": "client crypto policy"},
            "TLSv1.1": {"protocol_found": False, "refused": True, "handshake_completed": False,
                        "refusal_attributable_to_server": False,
                        "refusal_reason": "client crypto policy"},
        }
        verdict = edge.protocol_policy_verdict(attempts)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(sorted(verdict["protocols_with_no_evidence"]), ["TLSv1", "TLSv1.1"])

        raw = {protocol: {"protocol": protocol, "instrument": "raw ClientHello",
                          "outcome": "ALERT", "alert_description": "protocol_version",
                          "refusal_attributable_to_server": True}
               for protocol in ("TLSv1", "TLSv1.1")}
        resolved = edge.merge_legacy_observations(verdict, raw)
        self.assertEqual(resolved["verdict"], "POLICY ENFORCED", resolved["reason"])
        self.assertEqual(resolved["protocols_with_no_evidence"], [])
        for protocol in ("TLSv1", "TLSv1.1"):
            self.assertEqual(resolved["per_protocol"][protocol]["outcome"], "REFUSED")
            self.assertEqual(resolved["per_protocol"][protocol]["resolved_by"],
                             "raw ClientHello")

    def test_the_merge_never_softens_a_policy_violation(self):
        """A listener that actually accepts TLS 1.0 must stay a violation."""
        attempts = {
            "TLSv1.2": {"protocol_found": True, "cipher_found": True,
                        "handshake_completed": True, "verification_succeeded": True},
            "TLSv1.3": {"protocol_found": True, "cipher_found": True,
                        "handshake_completed": True, "verification_succeeded": True},
            "SSLv3": {"protocol_found": False, "refused": True, "handshake_completed": False,
                      "refusal_attributable_to_server": True},
            "TLSv1": {"protocol_found": True, "cipher_found": True,
                      "handshake_completed": True, "verification_succeeded": True},
            "TLSv1.1": {"protocol_found": False, "refused": True, "handshake_completed": False,
                        "refusal_attributable_to_server": False},
        }
        verdict = edge.protocol_policy_verdict(attempts)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("TLSv1", verdict["policy_violations"])
        raw = {"TLSv1": {"outcome": "SERVER_HELLO", "refusal_attributable_to_server": False,
                         "instrument": "raw ClientHello"},
               "TLSv1.1": {"outcome": "ALERT", "alert_description": "protocol_version",
                           "refusal_attributable_to_server": True,
                           "instrument": "raw ClientHello"}}
        resolved = edge.merge_legacy_observations(verdict, raw)
        # The unobservable entry resolves, but the real violation must survive it.
        self.assertEqual(resolved["verdict"], "NOT PROVEN")
        self.assertEqual(resolved["policy_violations"], ["TLSv1"])
        self.assertEqual(resolved["per_protocol"]["TLSv1"]["outcome"], "ACCEPTED")
        self.assertEqual(resolved["per_protocol"]["TLSv1.1"]["outcome"], "REFUSED")
        self.assertEqual(resolved["protocols_with_no_evidence"], [])

    def test_an_unresolved_raw_probe_stays_not_observable(self):
        attempts = {
            "TLSv1.2": {"protocol_found": True, "cipher_found": True,
                        "handshake_completed": True, "verification_succeeded": True},
            "TLSv1.3": {"protocol_found": True, "cipher_found": True,
                        "handshake_completed": True, "verification_succeeded": True},
            "SSLv3": {"protocol_found": False, "refused": True, "handshake_completed": False,
                      "refusal_attributable_to_server": True},
            "TLSv1": {"protocol_found": False, "refused": True, "handshake_completed": False,
                      "refusal_attributable_to_server": False},
            "TLSv1.1": {"protocol_found": False, "refused": True, "handshake_completed": False,
                        "refusal_attributable_to_server": False},
        }
        verdict = edge.protocol_policy_verdict(attempts)
        raw = {"TLSv1": {"outcome": "NO EVIDENCE", "error": "ConnectionRefusedError",
                         "instrument": "raw ClientHello"}}
        resolved = edge.merge_legacy_observations(verdict, raw)
        self.assertEqual(resolved["verdict"], "NOT PROVEN")
        self.assertIn("TLSv1", resolved["protocols_with_no_evidence"])
        self.assertEqual(resolved["per_protocol"]["TLSv1"]["still_unresolved_because"],
                         "NO EVIDENCE")


class ClientEvidencePublicationTests(unittest.TestCase):
    """A failing client run must still publish its own evidence.

    Both failing runs published a report whose ``verdicts`` held only the Tailscale
    boundary, because ``probe.run`` raised before the inner result file was read -
    so the per-protocol transcripts that explained the failure stayed on the
    ephemeral runner and could not be retrieved.
    """

    def setUp(self):
        self.source = (ROOT / "tools/foundation/runtime_tls_edge.py").read_text(encoding="utf-8")

    def test_the_inner_result_is_ingested_before_the_failure_is_raised(self):
        ingest = self.source.index('report["client_checks"] = verified["checks"]')
        raise_ = self.source.index("raise client_error")
        call = self.source.index('probe.run("verify-tls-edge-as-a-real-client"')
        self.assertLess(call, ingest, "the client result is still read after the call")
        self.assertLess(ingest, raise_, "the evidence is not kept before the failure propagates")
        self.assertIn("except Exception as exc:", self.source[call:raise_])

    def test_a_missing_client_result_is_reported_rather_than_silently_empty(self):
        self.assertIn("ABSENT: the client probe produced no result file", self.source)

    def test_the_raw_client_hello_evidence_is_published_and_not_whitelisted_away(self):
        """The instrument that resolved the legacy protocols must publish its record.

        Run 35216709160 resolved TLS 1.0/1.1 through the raw ClientHello probe and
        reached POLICY ENFORCED, but the published report carried no
        ``tls_protocol_raw_client_hello``: the ingestion copied a hardcoded pair of
        verdict keys, so the new evidence was dropped one layer above the defect
        that had just been fixed.
        """
        copied = re.search(r'for key in \(([^)]*)\):\s*\n\s*if key in verified',
                           self.source)
        self.assertIsNotNone(copied, "the verdict ingestion no longer copies by key list")
        keys = set(re.findall(r'"([a-z_]+)"', copied.group(1)))
        for required in ("tls_protocol_policy", "certificate_verification",
                         "tls_protocol_raw_client_hello"):
            self.assertIn(required, keys,
                          f"{required} is formed by the client probe but not published")
        # Every verdict key the inner probe writes must be on that list.
        inner = (ROOT / "tools/foundation/runtime_tls_edge_checks.py").read_text(encoding="utf-8")
        written = set(re.findall(r'result\["verdicts"\]\["([a-z_]+)"\]', inner))
        unpublished = written - keys
        self.assertEqual(unpublished, {"tls_protocol_attempts"},
                         "a verdict key is written by the probe but neither published nor "
                         "deliberately withheld: " + json.dumps(sorted(unpublished)))

    def test_the_refusal_summary_tolerates_a_half_finished_run(self):
        source = (ROOT / "tools/foundation/runtime_tls_edge.py").read_text(encoding="utf-8")
        start = source.index("def summarize_refusals(")
        end = source.index("def main()")
        namespace = {}
        exec(compile(source[start:end], "summarize", "exec"), namespace)
        summary = namespace["summarize_refusals"]({
            "tls_protocol_policy": {"per_protocol": {
                "TLSv1": {"outcome": "NOT OBSERVABLE", "reason": "client crypto policy"},
                "SSLv3": {"outcome": "REFUSED"}}}})
        self.assertEqual(summary["protocols_rejected_by_the_listener"], ["SSLv3"])
        self.assertEqual(summary["protocols_rejected_by_the_client_and_therefore_not_evidence"],
                         ["TLSv1"])
        self.assertEqual(summary["client_side_refusal_reasons"],
                         {"TLSv1": "client crypto policy"})
        self.assertFalse(summary["complete"], "a half-finished run must not claim completeness")

    def test_a_complete_run_reports_complete(self):
        source = (ROOT / "tools/foundation/runtime_tls_edge.py").read_text(encoding="utf-8")
        namespace = {}
        exec(compile(source[source.index("def summarize_refusals("):source.index("def main()")],
                     "summarize", "exec"), namespace)
        summary = namespace["summarize_refusals"]({
            "tls_protocol_policy": {"per_protocol": {"TLSv1": {"outcome": "REFUSED"}}},
            "certificate_verification": {"verify_return_code_without_ca": 20,
                                         "wrong_name_verify_return_code": 62}})
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["unrelated_ca_rejected"], 20)
        self.assertEqual(summary["hostname_mismatch_rejected"], 62)


if __name__ == "__main__":
    unittest.main()
