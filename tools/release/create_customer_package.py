"""Assemble an image-inclusive TOEFL House ERP customer package.

This provider/CI-side tool deliberately has no Docker build path.  It accepts
an already-built image archive, copies an explicit customer allowlist, and
writes a release manifest that binds the archive to the source revision and
dependency matrix used to build it.  It never copies ``product/data`` or any
site credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FILES = (
    "TOEFL House ERP.vbs",
    "product/docker-compose.yml",
    "product/windows/TOEFL House ERP.ps1",
    "product/windows/Run TOEFL House ERP.ps1",
    "product/windows/Check This PC.ps1",
    "product/windows/OWNER ACCEPTANCE GUIDE.txt",
    "product/windows/DAILY USE GUIDE.txt",
    "product/windows/Verify Package Image.ps1",
    "product/windows/Install TOEFL House ERP.cmd",
    "product/windows/Start TOEFL House ERP.cmd",
    "product/windows/Stop TOEFL House ERP.cmd",
    "product/windows/Repair TOEFL House ERP.cmd",
    "product/windows/Test Fresh Installation.ps1",
    "product/windows/Test Existing Installation.ps1",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,95}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_utf8(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8", newline="\n")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON metadata: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"metadata is not an object: {path}")
    return value


def dependency_manifest(source: Path) -> tuple[str, list[dict[str, object]]]:
    matrix_path = source / "docs/engineering/foundation-version-matrix.json"
    matrix_hash = sha256(matrix_path)
    components = matrix_path.read_text(encoding="utf-8")
    payload = json.loads(components)
    rows = []
    for component in payload.get("components", []):
        if not isinstance(component, dict) or "name" not in component:
            continue
        rows.append({
            key: component[key]
            for key in ("name", "selected_version", "commit", "digest", "tarball_sha256")
            if key in component
        })
    return matrix_hash, rows


def assert_inside(path: Path, root: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the selected output root") from exc


def copy_allowlist(source: Path, package: Path) -> None:
    for relative in ALLOWED_FILES:
        origin = source / relative
        if not origin.is_file() or origin.is_symlink():
            raise ValueError(f"required package component is missing or linked: {relative}")
        target = package / relative
        assert_inside(target, package, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)


def make_zip(package: Path) -> Path:
    archive = package.parent / f"{package.name}.zip"
    if archive.exists():
        raise ValueError(f"refusing to overwrite existing archive: {archive}")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as handle:
        for path in sorted(package.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"package contains a link: {path}")
            if path.is_file():
                handle.write(path, path.relative_to(package.parent).as_posix())
    return archive


def create_package(
    *,
    source: Path,
    output: Path,
    image_archive: Path,
    image_labels: dict,
    version: str,
    source_revision: str,
    provider_attestation: str,
) -> tuple[Path, Path, dict]:
    source = source.resolve()
    output = output.resolve()
    image_archive = image_archive.resolve()
    if not HEX40.fullmatch(source_revision):
        raise ValueError("source revision must be a full 40-character commit SHA")
    if not SAFE_VERSION.fullmatch(version):
        raise ValueError("version contains unsupported characters")
    if not image_archive.is_file() or image_archive.is_symlink():
        raise ValueError("a regular prebuilt image archive is required")
    if source == output or output.is_relative_to(source):
        raise ValueError("output must be outside the source repository")
    if image_labels.get("org.toefl-house.source-eol") != "lf-v1":
        raise ValueError("image lacks org.toefl-house.source-eol=lf-v1")
    if image_labels.get("org.toefl-house.source-revision") != source_revision:
        raise ValueError("image source revision does not match the requested package revision")
    if image_labels.get("org.toefl-house.release-version") != version:
        raise ValueError("image release version does not match the requested package version")

    package = output / f"TOEFL-House-ERP-Customer-{version}"
    if package.exists():
        raise ValueError(f"refusing to overwrite existing package: {package}")
    package.mkdir(parents=True)
    try:
        copy_allowlist(source, package)
        release = package / "product/release"
        release.mkdir(parents=True)
        archive = release / "toefl-house-erp-app.tar"
        shutil.copy2(image_archive, archive)
        archive_hash = sha256(archive)
        checksum = release / "toefl-house-erp-app.tar.sha256"
        write_utf8(checksum, archive_hash + "  toefl-house-erp-app.tar\n")
        matrix_hash, dependencies = dependency_manifest(source)
        manifest = {
            "schema_version": 1,
            "product": "TOEFL House ERP",
            "version": version,
            "release_status": "TEST PACKAGE - NO REAL DATA",
            "production_authorization": "REJECT",
            "source_revision": source_revision,
            "image": {
                "tag": "toefl-house-erp-app:customer",
                "archive": "product/release/toefl-house-erp-app.tar",
                "sha256": archive_hash,
                "size_bytes": archive.stat().st_size,
                "labels": image_labels,
            },
            "dependency_matrix_sha256": matrix_hash,
            "dependencies": dependencies,
            "provider_attestation": {
                "type": provider_attestation,
                "required_for_delivery": True,
            },
            "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        manifest_path = release / "release-manifest.json"
        write_utf8(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        write_utf8(release / "release-manifest.json.sha256", sha256(manifest_path) + "  release-manifest.json\n")
        instructions = f"""TOEFL HOUSE ERP - CUSTOMER PACKAGE {version}

This package contains a provider-built Linux application image. The customer
does not build Frappe, compile Docker images, use Git, or run database commands.

1. Install Docker Desktop for Windows 10/11 (64-bit) and complete WSL 2 setup.
2. Extract this complete folder to a local drive and double-click TOEFL House ERP.vbs.
3. Use Install on a genuinely new computer, then use Open / Start on later days.
4. Use the included Owner Readiness Guide and DAILY USE GUIDE.txt. They are
   acceptance instructions, not production approval.

Verify product/release/release-manifest.json and its checksum with the trusted
provider before use. The archive checksum detects corruption; the provider
attestation/signature is the identity check. Release status is TEST PACKAGE -
NO REAL DATA and production authorization is REJECT. Do not enter real student,
payroll or financial data until the owner gates are separately approved.
"""
        write_utf8(package / "READ ME FIRST.txt", instructions)
        archive_zip = make_zip(package)
        return package, archive_zip, manifest
    except Exception:
        # Keep the failure recoverable and obvious; never delete an existing
        # package or another output. The caller can inspect and remove only
        # this newly-created failed directory after review.
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-archive", type=Path, required=True)
    parser.add_argument("--image-labels", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--provider-attestation", default="GitHub Actions artifact attestation")
    args = parser.parse_args(argv)
    try:
        labels = load_json(args.image_labels)
        package, archive, manifest = create_package(
            source=args.source,
            output=args.output,
            image_archive=args.image_archive,
            image_labels=labels,
            version=args.version,
            source_revision=args.source_revision,
            provider_attestation=args.provider_attestation,
        )
        print(json.dumps({
            "package": str(package),
            "archive": str(archive),
            "archive_sha256": manifest["image"]["sha256"],
            "version": manifest["version"],
            "source_revision": manifest["source_revision"],
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"customer package creation failed safely: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
