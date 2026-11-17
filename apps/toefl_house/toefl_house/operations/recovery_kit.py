"""Create an owner-held recovery kit without saving private keys in ERP."""

import base64
import json
from pathlib import Path
import re
import secrets
import subprocess
from tempfile import TemporaryDirectory

import frappe
from werkzeug.wrappers import Response

from toefl_house.configuration.audit import require_authority


_KEY_LABEL = "TOEFL House ERP Backup Recovery"


def _verified_factory_release():
    from toefl_house.setup_presets.provider_release import has_verified_factory_release

    return has_verified_factory_release()


def _recovery_policy_exists():
    from toefl_house.operations.owner_configuration import _validated_backup_terms

    return bool(_validated_backup_terms())


def _gpg(home, *args, secret=None, data=None):
    command = ["/usr/bin/gpg", "--homedir", home, "--no-options", "--batch",
               "--no-tty", "--yes"]
    if secret is not None:
        command += ["--pinentry-mode", "loopback", "--passphrase-fd", "0"]
        data = secret + b"\n"
    result = subprocess.run(command + list(args), input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError("GnuPG recovery setup failed")
    return result.stdout


def _close_keyring(home):
    # Close the dedicated agent before its temporary keyring is removed.
    subprocess.run(["/usr/bin/gpgconf", "--homedir", home, "--kill", "gpg-agent"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=5, check=True)


def _prove_portable_kit(public, kit, fingerprint, passphrase):
    with TemporaryDirectory(prefix="th-recovery-check-") as home:
        try:
            _gpg(home, "--import", data=public.encode("ascii"))
            proof = secrets.token_bytes(32)
            ciphertext = _gpg(home, "--trust-model", "always", "--recipient",
                              fingerprint, "--encrypt", data=proof)
            # Import only the exported encryption subkey. The generated
            # primary and its original secret keyring are never used to verify.
            _gpg(home, "--import", data=kit)
            path = Path(home) / "proof.gpg"
            path.write_bytes(ciphertext)
            recovered = _gpg(home, "--decrypt", str(path), secret=passphrase)
            if not secrets.compare_digest(proof, recovered):
                raise RuntimeError("Portable recovery check did not recover the exact data")
        finally:
            _close_keyring(home)


def _generate_kit(passphrase):
    with TemporaryDirectory(prefix="th-recovery-key-") as home:
        try:
            _gpg(home, "--quick-generate-key", _KEY_LABEL, "rsa3072", "cert", "0",
                 secret=passphrase)
            listing = _gpg(home, "--with-colons", "--fingerprint", "--list-keys")
            match = re.search(rb"^fpr:(?:[^:\n]*:){8}([0-9A-F]{40}):", listing, re.M)
            if not match:
                raise RuntimeError("GnuPG did not return the generated key fingerprint")
            fingerprint = match[1].decode("ascii")
            _gpg(home, "--quick-add-key", fingerprint, "rsa3072", "encr", "0",
                 secret=passphrase)
            public = _gpg(home, "--armor", "--export", fingerprint).decode("ascii")
            kit = _gpg(home, "--export-secret-subkeys", fingerprint, secret=passphrase)
            if not public.startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----") or not kit:
                raise RuntimeError("GnuPG did not export the recovery kit")
            packets = _gpg(home, "--list-only", "--list-packets", data=kit).lower()
            if (b":secret sub key packet:" not in packets
                    or not re.search(rb"gnu[- ]dummy", packets)
                    or b"iter+salt s2k" not in packets):
                raise RuntimeError("GnuPG did not produce a protected decryption subkey")
        finally:
            _close_keyring(home)
    _prove_portable_kit(public, kit, fingerprint, passphrase)
    return {"public_key": public, "kit_b64": base64.b64encode(kit).decode("ascii"),
            "fingerprint": fingerprint}


@frappe.whitelist(methods=["POST"])
def create_recovery_kit(recovery_password):
    """Return an encrypted download and the associated public key to the Owner."""
    # Frappe's diagnostic recorder may inspect form_dict after this call.
    frappe.form_dict.pop("recovery_password", None)
    try:
        actor = require_authority("business_policy")
        if (frappe.db.get_value("User", actor, "user_type") != "System User"
                or not _verified_factory_release()):
            raise frappe.PermissionError("Recovery kit setup is unavailable for this installation")
        if frappe.request.host not in {"127.0.0.1:8000", "localhost:8000"}:
            raise frappe.PermissionError("Open ERP on this Windows computer to create a recovery kit")
        if _recovery_policy_exists():
            raise frappe.PermissionError("A recovery key is already configured. Keep the existing recovery kit.")
        if (not isinstance(recovery_password, str) or not 16 <= len(recovery_password) <= 128
                or not recovery_password.strip() or not recovery_password.isprintable()):
            raise frappe.ValidationError("Use a printable recovery passphrase of 16 to 128 characters")
        try:
            kit = _generate_kit(recovery_password.encode("utf-8"))
        except (OSError, RuntimeError, subprocess.SubprocessError, UnicodeError):
            raise frappe.ValidationError("Could not create the recovery kit. Try again.") from None
    finally:
        recovery_password = None
    return Response(json.dumps({"message": kit}), mimetype="application/json",
                    headers={"Cache-Control": "no-store, private"})
