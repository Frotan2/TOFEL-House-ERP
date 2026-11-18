"""Verify a developer's release authorization for a factory Windows install.

An installer receipt, a Windows publisher signature and customer-owned files
do not on their own authorize production use. This verifier trusts a
purpose-bound public key provisioned in the provider's application image.
"""
from datetime import datetime, timezone
from pathlib import Path
import re

from update_engine import (
    PRODUCT,
    UpdateError,
    _load_signature_envelope,
    _read_json_file,
    load_json_file,
    load_trust_store,
    rsa_pkcs1v15_sha256_verify,
    select_key,
)

RELEASE_NAME = "customer-release.json"
SIGNATURE_NAME = "customer-release.sig.json"
TRUST_PATH = Path("/product/customer-release-trust.json")
REVISION_PATH = Path("/product/customer-release-revision")
PURPOSE = "customer-installation-release"
GRANT_KIND = "toefl-house-erp-customer-release"
SIGNATURE_KIND = "toefl-house-erp-customer-release-signature"


def verify(activation_dir: Path, *, now: datetime | None = None) -> str:
    """Return the verified release id or raise without changing the site."""
    now = now or datetime.now(timezone.utc)
    grant, raw = _read_json_file(activation_dir / RELEASE_NAME, "release manifest", limit=8192)
    fields = {
        "schema_version", "document_type", "product", "release_id",
        "source_revision", "image_id", "windows_acceptance_sha256",
        "production_authorization",
    }
    if (grant.keys() not in (fields, fields | {"oci_manifest_digest"})
            or type(grant["schema_version"]) is not int
            or grant["schema_version"] != 1 or grant["document_type"] != GRANT_KIND
            or grant["product"] != PRODUCT or grant["production_authorization"] != "AUTHORIZED"):
        raise UpdateError("release.manifest.invalid", "production release authorization is invalid")
    for name, pattern in (
        ("release_id", r"[A-Za-z0-9][A-Za-z0-9._+\-]{0,95}"),
        ("source_revision", r"[0-9a-f]{40}"),
        ("image_id", r"sha256:[0-9a-f]{64}"),
        ("windows_acceptance_sha256", r"[0-9a-f]{64}"),
    ):
        if not isinstance(grant[name], str) or not re.fullmatch(pattern, grant[name]):
            raise UpdateError("release.manifest.invalid", f"production release {name} is invalid")
    identity = load_json_file(activation_dir / "installed-image-identity.json",
                              "installed image identity", limit=4096)
    runtime_image_id = identity.get("image_id")
    # The runtime image ID can be an OCI descriptor on newer Docker engines.
    # The release grant uses the verified archive config digest across engines.
    factory_image_id = identity.get("factory_release_image_id", runtime_image_id)
    accepted_image_ids = [grant["image_id"]]
    if "oci_manifest_digest" in grant:
        oci_digest = grant["oci_manifest_digest"]
        if not isinstance(oci_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", oci_digest):
            raise UpdateError("release.manifest.invalid", "production release OCI manifest digest is invalid")
        accepted_image_ids.append(oci_digest)
    if (type(identity.get("schema_version")) is not int or identity["schema_version"] != 1
            or identity.get("document_type") != "toefl-house-erp-installed-image"
            or identity.get("provenance") != "factory"
            or identity.get("source_revision") != grant["source_revision"]
            or runtime_image_id not in accepted_image_ids
            or factory_image_id != grant["image_id"]):
        raise UpdateError("release.manifest.invalid", "production approval belongs to a different factory image")
    try:
        revision = REVISION_PATH.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        raise UpdateError("release.manifest.invalid", "application image revision is unavailable") from None
    if revision != grant["source_revision"]:
        raise UpdateError("release.manifest.invalid", "production approval belongs to a different source revision")
    envelope = _load_signature_envelope(activation_dir / SIGNATURE_NAME, SIGNATURE_KIND,
                                        code="release.signature.invalid")
    key = select_key(load_trust_store(TRUST_PATH, now=now), envelope["key_id"], PURPOSE, now=now)
    if (key["algorithm"] != envelope["algorithm"]
            or not rsa_pkcs1v15_sha256_verify(key["modulus"], key["exponent"], raw, envelope["signature"])):
        raise UpdateError("release.signature.invalid", "production release signature did not verify")
    return grant["release_id"]
