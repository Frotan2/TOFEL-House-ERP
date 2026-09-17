"""Pure helpers for the operational TLS/edge boundary probe.

Kept free of any application or network dependency so the fiddly parts - the
certificate commands, the nginx policy text and the parsers for what ``openssl
s_client`` actually prints - can be exercised directly against real OpenSSL
output before a hosted run is spent on them. Parsing TLS negotiation output by
hand is where a probe like this quietly lies: a parser that never matches still
"passes" if its result is only recorded, so every parser here returns an explicit
``found`` flag and the probe fails closed when it is false.

The boundary being exercised is the one the pinned bench nginx template implies:
a front proxy that terminates TLS, redirects or refuses plaintext HTTP, sends
HSTS, restricts protocol versions, serves public files statically, and reaches
private files only through the application's own permission check via
``X-Accel-Redirect`` to an ``internal`` location.

What this module deliberately does not claim: a real tailnet. Joining one needs an
owner-provisioned auth key and ACL policy, so ``tailscale_boundary_verdict``
classifies that as ENVIRONMENT-BLOCKED and reports only what is genuinely
observable - which addresses the listener is bound to.
"""
import re

CA_COMMON_NAME = "Foundation Operational Boundary Test CA"
EDGE_HOST = "edge.foundation.internal"
WRONG_HOST = "wrong-name.foundation.internal"
BACKEND_HOST = "127.0.0.1"

# The intended policy. Anything older is refused at the listener, and the probe
# attempts each refused protocol so the refusal is observed rather than assumed.
ALLOWED_PROTOCOLS = ("TLSv1.2", "TLSv1.3")
REFUSED_PROTOCOLS = ("SSLv3", "TLSv1", "TLSv1.1")
#: The refused protocols an OpenSSL 3 client can still offer, so the listener's
#: refusal of them is observable rather than merely declared.
OFFERABLE_REFUSED_PROTOCOLS = ("TLSv1", "TLSv1.1")
#: OpenSSL 3 removed the ``-ssl3`` flag entirely - ``s_client`` answers "Unknown
#: option" and never opens a socket. No available client can offer SSLv3, so the
#: listener's exclusion of it is a configuration fact and is reported as such
#: instead of being counted as an observed refusal.
UNOFFERABLE_PROTOCOLS = ("SSLv3",)
UNOFFERABLE_REASON = (
    "OpenSSL 3 removed SSLv3 support and the -ssl3 flag with it, so s_client exits "
    "with a usage error and never attempts a handshake. No available client can offer "
    "SSLv3, which means the listener's refusal of it cannot be observed from here; it "
    "is excluded by the ssl_protocols directive, and that exclusion is recorded as "
    "declared rather than as observed.")

#: A client configuration relaxed enough to offer protocols the distribution's
#: default OpenSSL policy forbids. Only the refusal attempts use it: relaxing the
#: client is what makes the SERVER's refusal observable, and it is recorded so no
#: reader mistakes a relaxed client for a relaxed server. The allowed-protocol and
#: trust-control attempts stay on the distribution default.
PERMISSIVE_OPENSSL_CONF = """openssl_conf = openssl_init
[openssl_init]
ssl_conf = ssl_sect
[ssl_sect]
system_default = system_default_sect
[system_default_sect]
MinProtocol = None
CipherString = DEFAULT@SECLEVEL=0
Options = UnsafeLegacyRenegotiation
"""
HSTS_MAX_AGE = 63072000

# Recorded with the verdict so a reader can see which side of the boundary a
# certificate was trusted by.
TRUST_ANCHOR_NOTE = (
    "A private test CA generated inside the run. It proves the chain, the hostname "
    "binding and the verification behaviour are real; it is not a publicly trusted "
    "certificate and does not qualify a public edge."
)


def _p(*parts):
    return "/".join(str(part) for part in parts)


def ca_commands(directory, days=2):
    """Build a private CA: one key, one self-signed certificate."""
    directory = str(directory)
    return [
        ["openssl", "genpkey", "-algorithm", "rsa", "-pkeyopt", "rsa_keygen_bits:2048",
         "-out", _p(directory, "ca.key")],
        ["openssl", "req", "-x509", "-new", "-key", _p(directory, "ca.key"),
         "-sha256", "-days", str(days), "-out", _p(directory, "ca.pem"),
         "-subj", "/CN=" + CA_COMMON_NAME,
         "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "keyUsage=critical,keyCertSign,cRLSign"],
    ]


def server_cert_commands(directory, host=EDGE_HOST, days=2, name="server"):
    """Issue a leaf certificate for ``host`` from the private CA.

    The hostname is placed in ``subjectAltName`` as well as the CN, because
    modern clients - including the OpenSSL used here - match on the SAN and
    ignore the CN. A certificate with the name only in the CN would make the
    hostname-mismatch negative control pass for the wrong reason.
    """
    directory = str(directory)
    key = _p(directory, name + ".key")
    csr = _p(directory, name + ".csr")
    cert = _p(directory, name + ".pem")
    return [
        ["openssl", "genpkey", "-algorithm", "rsa", "-pkeyopt", "rsa_keygen_bits:2048",
         "-out", key],
        ["openssl", "req", "-new", "-key", key, "-out", csr, "-subj", "/CN=" + host],
        ["openssl", "x509", "-req", "-in", csr, "-CA", _p(directory, "ca.pem"),
         "-CAkey", _p(directory, "ca.key"), "-CAcreateserial", "-out", cert,
         "-days", str(days), "-sha256",
         "-extfile", "/dev/stdin"],
    ], {"certificate": cert, "key": key, "san": "DNS:" + host,
        "extensions_stdin": ("basicConstraints=CA:FALSE\n"
                             "keyUsage=critical,digitalSignature,keyEncipherment\n"
                             "extendedKeyUsage=serverAuth\n"
                             "subjectAltName=DNS:" + host + "\n")}


def verify_chain_command(directory, name="server"):
    """``openssl verify`` against the private CA - the chain check, independent
    of any TLS handshake."""
    directory = str(directory)
    return ["openssl", "verify", "-CAfile", _p(directory, "ca.pem"),
            _p(directory, name + ".pem")]


def fingerprint_command(directory, name="server"):
    return ["openssl", "x509", "-in", _p(directory, name + ".pem"), "-noout",
            "-fingerprint", "-sha256"]


def s_client_command(port, *, protocol=None, cafile=None, verify_hostname=None,
                     connect=BACKEND_HOST, servername=None, empty_store=None):
    """Build an ``openssl s_client`` invocation.

    Two details that decide whether the result means anything:

    * ``s_client`` does NOT verify the hostname unless ``-verify_hostname`` is
      given - it only validates the chain. Without the flag a certificate issued
      for the wrong name still reports ``Verify return code: 0``, so the hostname
      control would pass for the wrong reason. It is therefore passed explicitly.
    * ``-CAfile /dev/null`` is not "no trust anchor": OpenSSL 3 fails while
      *loading* the store (``no certificate or crl found``) and never attempts a
      handshake, which proves nothing about the server. The real control is an
      unrelated CA, which produces a genuine chain-validation failure.
    """
    command = ["openssl", "s_client", "-connect", f"{connect}:{port}"]
    if servername:
        command += ["-servername", servername]
    if verify_hostname:
        command += ["-verify_hostname", verify_hostname]
    if protocol:
        command += [protocol_flag(protocol)]
    if cafile:
        command += ["-CAfile", str(cafile)]
    elif empty_store:
        command += ["-CAfile", str(empty_store)]
    return command


def protocol_flag(protocol):
    """The ``s_client`` flag that pins a single protocol version."""
    return {
        "SSLv3": "-ssl3", "TLSv1": "-tls1", "TLSv1.1": "-tls1_1",
        "TLSv1.2": "-tls1_2", "TLSv1.3": "-tls1_3",
    }[protocol]


def nginx_tls_conf(*, lab, bench_dir, site, http_port, https_port, backend_port,
                   certificate, key, host=EDGE_HOST, hsts_maxage=HSTS_MAX_AGE,
                   protocols=("TLSv1.2", "TLSv1.3"), bind="127.0.0.1",
                   ciphers="EECDH+AESGCM:EDH+AESGCM"):
    """A front proxy that terminates TLS, following the pinned bench template.

    The TLS policy here is not invented for this probe: ``ssl_protocols``,
    ``ssl_ciphers``, ``ssl_ecdh_curve``, the session settings, the HSTS value and
    the four accompanying security headers are the ones the pinned bench nginx
    template (frappe/bench ``config/templates/nginx.conf``) renders for a site
    with a certificate, and ``X-Forwarded-Proto $scheme`` is the header that
    template sends. Matching it means the evidence is about the intended
    production shape rather than about a policy written to be easy to pass.

    The plaintext ``return 301 https://$host$request_uri`` redirect is the
    template's too. One deliberate deviation: the template hardcodes ports 80 and
    443, and binding those needs root, so this probe listens on unprivileged ports
    and the redirect carries the TLS port explicitly. The port is not part of the
    security claim; the fact that plaintext answers with a redirect and nothing
    else is.

    ``bind`` is parameterized because that is the only part of a tailnet-shaped
    deployment this environment can honestly exercise: a listener bound to one
    address is not reachable on the others. It is not a tailnet and is never
    reported as one.

    Everything the recovery harness proved about the plaintext proxy is kept:
    ``root`` at the sites directory, ``try_files /<site>/public/$uri @webserver``,
    the ``internal`` ``/protected/`` location that ``X-Accel-Redirect`` needs, and
    a Host allowlist rather than client-supplied routing.
    """
    return f"""pid {lab}/nginx-tls.pid;
error_log {lab}/nginx-tls-error.log;
events {{ worker_connections 128; }}
http {{
 include /etc/nginx/mime.types;
 access_log off;
 client_body_temp_path {lab}/nginx-tls-body;
 proxy_temp_path {lab}/nginx-tls-proxy;
 map $host $foundation_site {{ default ''; {host} {site}; }}

 upstream foundation-frappe {{
  server {backend_port} fail_timeout=0;
 }}

 # The plaintext listener exists only to refuse plaintext use: it answers with a
 # redirect and never proxies, so no request - and no spoofed X-Forwarded-Proto -
 # can reach the application without crossing the TLS boundary.
 server {{
  listen {bind}:{http_port};
  server_name {host};
  return 301 https://{host}:{https_port}$request_uri;
 }}

 server {{
  listen {bind}:{https_port} ssl;
  server_name {host};
  root {bench_dir}/sites;

  ssl_certificate {certificate};
  ssl_certificate_key {key};
  ssl_session_timeout 5m;
  ssl_session_cache shared:FoundationTLS:10m;
  ssl_session_tickets off;
  ssl_protocols {' '.join(protocols)};
  ssl_ciphers {ciphers};
  ssl_ecdh_curve secp384r1;
  ssl_prefer_server_ciphers on;

  add_header X-Frame-Options "SAMEORIGIN";
  add_header Strict-Transport-Security "max-age={hsts_maxage}; includeSubDomains; preload";
  add_header X-Content-Type-Options nosniff;
  add_header X-XSS-Protection "1; mode=block";
  add_header Referrer-Policy "same-origin, strict-origin-when-cross-origin";

  if ($foundation_site = '') {{ return 444; }}
  location /assets/ {{ alias {bench_dir}/sites/assets/; }}
  location ~ ^/protected/(.*) {{
   internal;
   try_files /{site}/$1 =404;
  }}
  location ~* ^/files/.*.(htm|html|svg|xml) {{
   add_header Content-disposition "attachment";
   try_files /{site}/public/$uri @webserver;
  }}
  location / {{
   try_files /{site}/public/$uri @webserver;
  }}
  location @webserver {{
   proxy_http_version 1.1;
   proxy_set_header X-Frappe-Site-Name $foundation_site;
   proxy_set_header Host $host;
   proxy_set_header X-Forwarded-Proto $scheme;
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   proxy_set_header X-Use-X-Accel-Redirect True;
   proxy_read_timeout 120;
   proxy_redirect off;
   proxy_pass http://foundation-frappe;
  }}
 }}
}}
"""


def parse_s_client(output):
    """Read the negotiated protocol, cipher, verification result and peer name.

    Every field carries a ``found`` flag. ``openssl s_client`` output varies
    between versions and between a successful and a refused handshake, and a
    parser that silently returns ``None`` would let a probe record "TLS 1.0 was
    refused" when in fact it had parsed nothing at all.
    """
    report = {
        "protocol": None, "protocol_found": False,
        "cipher": None, "cipher_found": False,
        "verify_return_code": None, "verify_return_code_found": False,
        "verification_succeeded": None,
        "subject": None, "subject_found": False,
        "issuer": None, "issuer_found": False,
        "subject_alt_names": [], "subject_alt_names_found": False,
        "handshake_completed": False,
        "handshake_read_bytes": None,
        "protocol_source": None,
        "protocol_attempted": None,
        "client_cannot_attempt": False,
        "refused": False,
        "refusal_reason": None,
        "refusal_attributable_to_server": None,
        "is_server_evidence": False,
        "output_bytes": len(output or ""),
    }
    if not output:
        return report

    # OpenSSL 3 prints the negotiated pair in two different shapes depending on the
    # version: a TLS 1.2 session includes an "SSL-Session:" block with indented
    # "Protocol  :" and "Cipher    :" lines, while a TLS 1.3 session does not print
    # that block at all and only reports the one-line "New, TLSv1.3, Cipher is ...".
    # Reading only the indented form silently reports "TLS 1.3 refused", so the
    # one-line form is parsed first and the block is the fallback.
    match = re.search(r"^New,\s*(\S+),\s*Cipher is\s*(\S+)\s*$", output, re.MULTILINE)
    if match:
        report["protocol"] = None if match.group(1) == "(NONE)" else match.group(1)
        report["protocol_found"] = match.group(1) not in ("(NONE)",)
        report["cipher"] = None if match.group(2) in ("(NONE)", "0000") else match.group(2)
        report["cipher_found"] = report["cipher"] is not None
        report["protocol_source"] = "New/Cipher line"
        if report["protocol"] is None:
            # The refused handshake still reports the version the client offered in
            # its SSL-Session block. Keep it as "attempted" so the evidence shows
            # what was actually offered, without claiming it was negotiated.
            offered = re.search(r"^\s*Protocol\s*:\s*(\S+)\s*$", output, re.MULTILINE)
            if offered and offered.group(1) not in ("(NONE)",):
                report["protocol_attempted"] = offered.group(1)
    else:
        match = re.search(r"^\s*Protocol\s*:\s*(\S+)\s*$", output, re.MULTILINE)
        if match:
            report["protocol"] = match.group(1)
            report["protocol_found"] = True
        match = re.search(r"^\s*Cipher\s*:\s*(\S+)\s*$", output, re.MULTILINE)
        if match:
            report["cipher"] = None if match.group(1) in ("(NONE)", "0000") else match.group(1)
            report["cipher_found"] = report["cipher"] is not None
        report["protocol_source"] = "SSL-Session block"
    match = re.search(r"Verify return code:\s*(-?\d+)\s*\(([^)]*)\)", output)
    if match:
        report["verify_return_code"] = int(match.group(1))
        report["verify_return_code_found"] = True
        report["verify_return_code_text"] = match.group(2)
        # A refused handshake prints "Verify return code: 0 (ok)" even though no
        # certificate was ever exchanged, so the code is only meaningful once a
        # cipher was agreed. Reporting success from that line would be a lie.
        report["verification_succeeded"] = (
            match.group(1) == "0" if report["cipher_found"] else None)
    match = re.search(r"^\s*\d+\s+s:(.+)$", output, re.MULTILINE)
    if match:
        report["subject"] = match.group(1).strip()
        report["subject_found"] = True
    match = re.search(r"^\s*i:(.+)$", output, re.MULTILINE)
    if match:
        report["issuer"] = match.group(1).strip()
        report["issuer_found"] = True
    match = re.search(r"X509v3 Subject Alternative Name:\s*\n\s*(.+)", output)
    if match:
        report["subject_alt_names"] = [
            entry.strip() for entry in match.group(1).split(",") if entry.strip()]
        report["subject_alt_names_found"] = True
    read_match = re.search(r"SSL handshake has read (\d+) bytes", output)
    report["handshake_read_bytes"] = int(read_match.group(1)) if read_match else None
    # A cipher being agreed is the only unambiguous sign the handshake completed.
    # Bytes read is not: a fatal alert is also read.
    report["handshake_completed"] = bool(report["cipher_found"])
    # Distinguish a refusal caused by the SERVER from one caused by the CLIENT's
    # own OpenSSL policy. Only the first says anything about the boundary being
    # exercised; conflating them is how a probe ends up "proving" a policy that
    # the listener never enforced.
    client_side = re.search(
        r"(no protocols available|unsupported protocol|no cipher match|"
        r"security level does not allow)", output)
    server_side = re.search(
        r"(alert protocol version|alert handshake failure|alert internal error|"
        r"sslv3 alert|tlsv1 alert|SSL alert number|handshake failure|"
        r"wrong version number)", output)
    load_error = re.search(r"(no certificate or crl found|error setting|Error loading)", output)
    usage_error = re.search(r"(Unknown option|Use -help|unknown option|invalid option)", output)
    if usage_error:
        report["refusal_reason"] = ("CLIENT CANNOT ATTEMPT: this OpenSSL build has no such "
                                    "option, so no socket was ever opened")
        report["refusal_attributable_to_server"] = None
        report["client_cannot_attempt"] = True
    elif client_side:
        report["refusal_reason"] = "CLIENT-SIDE: the local OpenSSL could not offer this protocol"
        report["refusal_attributable_to_server"] = False
    elif server_side:
        report["refusal_reason"] = "SERVER-SIDE: the listener rejected the offered protocol"
        report["refusal_attributable_to_server"] = True
    elif load_error:
        report["refusal_reason"] = "NO HANDSHAKE ATTEMPTED: the trust store failed to load"
        report["refusal_attributable_to_server"] = False
    else:
        report["refusal_reason"] = None
        report["refusal_attributable_to_server"] = None
        report["client_cannot_attempt"] = False
    match = re.search(r"Verification error:\s*(.+)$", output, re.MULTILINE)
    if match:
        report["verification_error_text"] = match.group(1).strip()
    report["verification_ok_line"] = bool(re.search(r"^Verification:\s*OK\s*$", output,
                                                    re.MULTILINE))
    report["refused"] = bool(client_side or server_side or load_error or usage_error
                             or not report["cipher_found"])
    # Anything that did not reach the server, or whose failure cannot be attributed,
    # is not evidence about the server.
    report["is_server_evidence"] = bool(report["cipher_found"]) or bool(
        server_side and not client_side and not usage_error)
    return report


def parse_certificate_text(output):
    """Read the fields the probe needs from ``openssl x509 -text -noout``.

    The SAN is checked on the certificate file itself rather than from the
    handshake, because ``s_client`` does not print the extension block.
    """
    report = {"subject_alt_names": [], "subject_alt_names_found": False,
              "common_name": None, "not_after": None, "is_ca": None,
              "signature_algorithm": None, "output_bytes": len(output or "")}
    if not output:
        return report
    match = re.search(r"Subject:\s*(.+)$", output, re.MULTILINE)
    if match:
        report["subject"] = match.group(1).strip()
        cn = re.search(r"CN\s*=\s*([^,/]+)", match.group(1))
        if cn:
            report["common_name"] = cn.group(1).strip()
    match = re.search(r"X509v3 Subject Alternative Name:\s*\n\s*(.+)", output)
    if match:
        report["subject_alt_names"] = [entry.strip() for entry in match.group(1).split(",")
                                       if entry.strip()]
        report["subject_alt_names_found"] = True
    match = re.search(r"Not After\s*:\s*(.+)$", output, re.MULTILINE)
    if match:
        report["not_after"] = match.group(1).strip()
    match = re.search(r"Signature Algorithm:\s*(\S+)", output)
    if match:
        report["signature_algorithm"] = match.group(1)
    report["is_ca"] = ("CA:TRUE" in output)
    return report


def parse_hsts(value):
    """Parse a ``Strict-Transport-Security`` header value."""
    report = {"present": bool(value), "raw": value, "max_age": None,
              "include_subdomains": False, "preload": False, "well_formed": False}
    if not value:
        return report
    parts = [part.strip() for part in value.split(";") if part.strip()]
    for part in parts:
        lowered = part.lower()
        if lowered.startswith("max-age="):
            digits = part.split("=", 1)[1].strip().strip('"')
            if digits.isdigit():
                report["max_age"] = int(digits)
        elif lowered == "includesubdomains":
            report["include_subdomains"] = True
        elif lowered == "preload":
            report["preload"] = True
    report["well_formed"] = report["max_age"] is not None
    return report


def protocol_policy_verdict(observed, unofferable=()):
    """Compare what each protocol attempt actually did against the policy.

    ``observed`` maps a protocol name to the parsed ``s_client`` report for an
    attempt pinned to that protocol. A protocol is *refused* when the handshake
    did not complete or verification failed for a protocol reason; it is
    *accepted* when a cipher was negotiated. The verdict fails closed if any
    attempt produced no parseable evidence at all.
    """
    per_protocol = {}
    for protocol, report in observed.items():
        # A protocol no available client can offer is classified first: it is not a
        # missing observation about the listener, it is a known limit of the clients,
        # and lumping it in with "no evidence" would fail a run for a reason nobody
        # could act on. If it somehow negotiated, normal handling applies instead.
        if ((protocol in unofferable or report.get("client_cannot_attempt"))
                and not report.get("cipher_found")):
            per_protocol[protocol] = {
                "outcome": "NOT OFFERABLE BY ANY AVAILABLE CLIENT",
                "negotiated": False,
                "expected": "ACCEPTED" if protocol in ALLOWED_PROTOCOLS else "REFUSED",
                "reason": report.get("refusal_reason") or UNOFFERABLE_REASON,
                "matches_policy": True,
                "counts_against_the_policy": False,
            }
            continue
        if not report.get("protocol_found") and not report.get("refused") \
                and not report.get("handshake_completed"):
            per_protocol[protocol] = {"outcome": "NO EVIDENCE",
                                      "negotiated": None, "expected": None}
            continue
        negotiated = bool(report.get("cipher_found") and report.get("handshake_completed")
                          and report.get("verification_succeeded") is not False)
        # Only a refusal the SERVER caused is evidence about the boundary. A refusal
        # caused by the client's own OpenSSL policy, a client that cannot offer the
        # protocol at all, or a failure that cannot be attributed, all leave the
        # listener's behaviour unobserved - and an unobserved behaviour must never be
        # recorded as enforced.
        if not negotiated and report.get("refusal_attributable_to_server") is not True:
            unofferable_now = protocol in unofferable or report.get("client_cannot_attempt")
            per_protocol[protocol] = {
                "outcome": ("NOT OFFERABLE BY ANY AVAILABLE CLIENT" if unofferable_now
                            else "NOT OBSERVABLE"),
                "negotiated": False,
                "expected": "ACCEPTED" if protocol in ALLOWED_PROTOCOLS else "REFUSED",
                "reason": report.get("refusal_reason") or (
                    UNOFFERABLE_REASON if unofferable_now else
                    "the attempt produced no parseable evidence either way"),
                "matches_policy": bool(unofferable_now),
                "counts_against_the_policy": not unofferable_now,
            }
            continue
        expected_allowed = protocol in ALLOWED_PROTOCOLS
        per_protocol[protocol] = {
            "outcome": "ACCEPTED" if negotiated else "REFUSED",
            "negotiated": negotiated,
            "expected": "ACCEPTED" if expected_allowed else "REFUSED",
            "refusal_reason": report.get("refusal_reason"),
            "protocol_reported": report.get("protocol"),
            "cipher": report.get("cipher"),
            "verify_return_code": report.get("verify_return_code"),
            "matches_policy": negotiated == expected_allowed,
        }
    unobserved = [name for name, value in per_protocol.items()
                  if value["outcome"] in ("NO EVIDENCE", "NOT OBSERVABLE")]
    unofferable_names = [name for name, value in per_protocol.items()
                         if value["outcome"] == "NOT OFFERABLE BY ANY AVAILABLE CLIENT"]
    # Only a real observation can violate the policy, and it violates it in either
    # direction: an allowed protocol being refused, or a refused protocol being
    # accepted. Unobserved and unofferable protocols are handled by their own lists
    # so a missing observation is never laundered into a mismatch or into a pass.
    mismatches = [name for name, value in per_protocol.items()
                  if value["outcome"] in ("ACCEPTED", "REFUSED")
                  and not value["matches_policy"]]
    enforced = not unobserved and not mismatches
    reason = ("every allowed protocol negotiated and every refused protocol a client could "
              "offer was rejected by the listener" if enforced else
              ("the listener's behaviour was not observed for: " + ", ".join(sorted(unobserved))
               if unobserved else
               "policy violated by: " + ", ".join(sorted(mismatches))))
    if enforced and unofferable_names:
        reason += ("; " + ", ".join(sorted(unofferable_names)) + " could not be offered by any "
                   "available client and is excluded by configuration only")
    return {
        "allowed_by_policy": list(ALLOWED_PROTOCOLS),
        "refused_by_policy": list(REFUSED_PROTOCOLS),
        "observed_refusals": sorted(name for name, value in per_protocol.items()
                                    if value["outcome"] == "REFUSED"),
        "not_offerable_by_any_client": sorted(unofferable_names),
        "per_protocol": per_protocol,
        "protocols_with_no_evidence": unobserved,
        "policy_violations": mismatches,
        "verdict": "POLICY ENFORCED" if enforced else "NOT PROVEN",
        "reason": reason,
        "unofferable_reason": UNOFFERABLE_REASON if unofferable_names else None,
    }


def trust_verdict(with_ca, without_ca, wrong_name_ca=None):
    """Verdict on whether verification is genuinely enforced.

    Three observations, all required: the handshake verifies with the private CA,
    fails without a trust anchor, and - when a certificate for the wrong hostname
    is served - fails on the name rather than passing because verification was
    switched off. A probe that only checked the first would pass on a listener
    configured with verification disabled.
    """
    trusted = bool(with_ca.get("verification_succeeded"))
    untrusted_failed = without_ca.get("verification_succeeded") is False \
        or without_ca.get("refused") is True
    result = {
        "verifies_with_the_private_ca": trusted,
        "fails_without_a_trust_anchor": untrusted_failed,
        "verify_return_code_with_ca": with_ca.get("verify_return_code"),
        "verify_return_code_without_ca": without_ca.get("verify_return_code"),
        "trust_anchor_note": TRUST_ANCHOR_NOTE,
    }
    if wrong_name_ca is not None:
        name_failed = wrong_name_ca.get("verification_succeeded") is False \
            or wrong_name_ca.get("refused") is True
        result["fails_on_a_hostname_mismatch"] = name_failed
        result["wrong_name_verify_return_code"] = wrong_name_ca.get("verify_return_code")
        result["hostname_binding_enforced"] = name_failed
    else:
        result["fails_on_a_hostname_mismatch"] = None
        result["hostname_binding_enforced"] = None
    result["verification_enforced"] = bool(
        trusted and untrusted_failed
        and (result["hostname_binding_enforced"] is not False))
    result["verdict"] = ("VERIFICATION ENFORCED" if result["verification_enforced"]
                         else "NOT PROVEN")
    return result


def tailscale_boundary_verdict(listen_addresses, *, auth_key_available=False,
                              tailscale_binary=None):
    """Classify the tailnet boundary honestly.

    Joining a real tailnet requires an owner-provisioned auth key and an ACL
    policy, neither of which this session has. Rather than simulating a tailnet
    and calling it proven, this reports the one observable fact - which addresses
    the listener is bound to - and classifies the rest ENVIRONMENT-BLOCKED.
    """
    # Addresses arrive as "host:port" or bare "host". The binding decision is made
    # by the host part alone - but a bare IPv6 wildcard ("::") also contains a
    # colon, so the wildcard forms are matched before any splitting.
    wildcard_hosts = ("0.0.0.0", "*", "::", "[::]")

    def is_wildcard(address):
        text = str(address).strip()
        if text in wildcard_hosts:
            return True
        if text.startswith("["):
            return text.split("]", 1)[0].lstrip("[") in ("::", "*")
        return text.rsplit(":", 1)[0] in ("0.0.0.0", "*") if ":" in text else False

    wildcard = [address for address in listen_addresses if is_wildcard(address)]
    return {
        "status": "ENVIRONMENT-BLOCKED" if not auth_key_available else "EXECUTED",
        "tailscale_binary_present": bool(tailscale_binary),
        "owner_inputs_required": [
            "a tailnet auth key or an OAuth client with permission to register a node",
            "the ACL policy that defines which identities may reach this service",
            "the decision of whether the service is tailnet-only or also publicly reachable",
        ],
        "listen_addresses_observed": list(listen_addresses),
        "bound_to_every_interface": bool(wildcard),
        "wildcard_addresses": wildcard,
        "what_is_proven": ("the listener is bound to explicit addresses rather than to every "
                           "interface, which is the binding shape a tailnet-only service needs"
                           if not wildcard else
                           "the listener is bound to every interface, so it is NOT tailnet-only"),
        "what_is_not_proven": (
            "no tailnet was joined, no node was registered, no ACL was evaluated and no "
            "cross-node connection was made; a private listener on an ephemeral runner is not "
            "a tailnet boundary and is never reported as one"),
        "not_simulated": True,
    }


def decode_proc_net_listeners(text):
    """Decode listening sockets from ``/proc/net/tcp`` or ``/proc/net/tcp6`` text.

    The kernel prints addresses in host byte order, so ``0100007F:4844`` is
    127.0.0.1:18500 and ``00000000:006F`` is 0.0.0.0:111. Reading this with
    ``ss`` would depend on a package being installed; ``/proc`` always is, and it
    reports what the kernel actually bound rather than what a tool reports.

    Only state ``0A`` (LISTEN) rows are returned.
    """
    listeners = []
    for line in (text or "").splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[3] != "0A" or fields[0].endswith("local_address"):
            continue
        local = fields[1]
        if ":" not in local:
            continue
        address, port_hex = local.rsplit(":", 1)
        try:
            port = int(port_hex, 16)
        except ValueError:
            continue
        listeners.append({"address": decode_kernel_address(address), "port": port,
                          "raw": local, "family": 6 if len(address) == 32 else 4})
    return listeners


def decode_kernel_address(hex_address):
    """Turn one kernel address field into the dotted/colon form a human reads."""
    text = (hex_address or "").strip()
    if len(text) == 8:
        octets = [int(text[index:index + 2], 16) for index in (6, 4, 2, 0)]
        return ".".join(str(value) for value in octets)
    if len(text) == 32:
        # Four 32-bit words, each little-endian.
        groups = []
        for word in range(0, 32, 8):
            chunk = text[word:word + 8]
            ordered = "".join(chunk[index:index + 2] for index in (6, 4, 2, 0))
            groups.append(ordered[0:4])
            groups.append(ordered[4:8])
        if all(group == "0000" for group in groups):
            return "::"
        if groups[0:6] == ["0000"] * 6 and groups[6] == "0000" and groups[7] == "0001":
            return "::1"
        compact = ":".join(group.lstrip("0") or "0" for group in groups)
        return compact
    return text


def binding_shape(listeners, ports):
    """Report how each expected port is bound, from decoded kernel state.

    A port that is not listening at all is reported as absent rather than being
    quietly skipped: a proxy that failed to bind must not produce a "bound to the
    intended interface" verdict.
    """
    shape = {}
    for port in ports:
        rows = [row for row in listeners if row["port"] == int(port)]
        if not rows:
            shape[str(port)] = {"listening": False, "addresses": [],
                                "bound_to_every_interface": None}
            continue
        addresses = [row["address"] for row in rows]
        shape[str(port)] = {
            "listening": True,
            "addresses": addresses,
            "raw": [row["raw"] for row in rows],
            "families": sorted({row["family"] for row in rows}),
            "bound_to_every_interface": any(
                address in ("0.0.0.0", "::", "*") for address in addresses),
        }
    return shape
