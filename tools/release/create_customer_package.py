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
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

if __package__:
    from .verify_ci_gates import MAX_EVIDENCE_BYTES, validate_gate_evidence
else:
    from verify_ci_gates import MAX_EVIDENCE_BYTES, validate_gate_evidence


ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FILES = (
    "TOEFL House ERP.vbs",
    "product/docker-compose.yml",
    "product/windows/TOEFL House ERP.ps1",
    "product/windows/Run TOEFL House ERP.ps1",
    "product/windows/Prepare This PC.ps1",
    "product/windows/Import Offline Runtime.ps1",
    "product/windows/Check This PC.ps1",
    "product/windows/OWNER ACCEPTANCE GUIDE.txt",
    "product/windows/OWNER HANDBOOK.txt",
    "product/windows/DAILY USE GUIDE.txt",
    "product/windows/Verify Package Image.ps1",
    "product/windows/Install TOEFL House ERP.cmd",
    "product/windows/Start TOEFL House ERP.cmd",
    "product/windows/Stop TOEFL House ERP.cmd",
    "product/windows/Backup TOEFL House ERP.cmd",
    "product/windows/Backup TOEFL House ERP.ps1",
    "product/windows/Repair TOEFL House ERP.cmd",
    "product/windows/Test Fresh Installation.ps1",
    "product/windows/Test Existing Installation.ps1",
    # Provider-reviewed signed update workflow (channel remains disabled).
    "product/windows/Update TOEFL House ERP.ps1",
    "product/windows/updater-strings.json",
    "product/updates/channel.json",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,95}$")
MAX_RELEASE_ASSET_BYTES = 2 * 1024 ** 3
IMAGE_TAG = "toefl-house-erp-app:local"
METADATA_LIMIT = 4 * 1024 * 1024
MATRIX_FILE = "docs/engineering/foundation-version-matrix.json"


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


def load_gate_evidence(path: Path, source_revision: str) -> dict:
    """Require the exact-SHA hosted gate receipt before any package output."""
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_EVIDENCE_BYTES:
        raise ValueError("a bounded, regular CI gate evidence file is required")
    evidence = load_json(path)
    return validate_gate_evidence(evidence, source_revision)


def archive_identity(path: Path, supplied_labels: dict) -> tuple[dict[str, str], str]:
    """Bind the labels to a single saved image without extracting its files."""
    try:
        with tarfile.open(path, "r:*") as archive:
            members = {}
            for member in archive:
                if member.name in members:
                    raise ValueError(f"duplicate image archive member: {member.name}")
                members[member.name] = member

            def regular_member(name: str) -> tarfile.TarInfo:
                if (not isinstance(name, str) or not name or "\\" in name
                        or PurePosixPath(name).is_absolute()
                        or ".." in PurePosixPath(name).parts):
                    raise ValueError("invalid image archive member path")
                member = members.get(name)
                if member is None or not member.isfile():
                    raise ValueError(f"missing or non-regular image archive member: {name}")
                return member

            def metadata(name: str) -> bytes:
                member = regular_member(name)
                if member.size > METADATA_LIMIT:
                    raise ValueError(f"image metadata is too large: {name}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ValueError(f"cannot read image metadata: {name}")
                with handle:
                    data = handle.read()
                if len(data) != member.size:
                    raise ValueError(f"truncated image metadata: {name}")
                return data

            manifest = json.loads(metadata("manifest.json"))
            if not isinstance(manifest, list) or len(manifest) != 1 or not isinstance(manifest[0], dict):
                raise ValueError("image archive must contain exactly one manifest image")
            entry = manifest[0]
            if entry.get("RepoTags") != [IMAGE_TAG]:
                raise ValueError(f"image archive must contain only the {IMAGE_TAG} tag")
            config_bytes = metadata(entry.get("Config"))
            config_hash = hashlib.sha256(config_bytes).hexdigest()
            if entry["Config"] not in (f"{config_hash}.json", f"blobs/sha256/{config_hash}"):
                raise ValueError("image config filename does not match its SHA-256 digest")
            config = json.loads(config_bytes)
            if not isinstance(config, dict) or not isinstance(config.get("config"), dict):
                raise ValueError("image config metadata is not an object")
            # The customer runs the provider's Linux/amd64 appliance under
            # Docker Desktop. A Windows container could carry the expected
            # labels, but would invalidate our Linux-only runtime security
            # assumptions (including the setuptools Windows advisory scope).
            if config.get("os") != "linux" or config.get("architecture") != "amd64":
                raise ValueError("customer application image must be linux/amd64")
            labels = config["config"].get("Labels")
            if (not isinstance(labels, dict)
                    or not all(isinstance(k, str) and isinstance(v, str) for k, v in labels.items())):
                raise ValueError("image config labels must be a string mapping")
            if labels != supplied_labels:
                raise ValueError("image archive config labels do not match the supplied image labels")
            layers = entry.get("Layers")
            rootfs = config.get("rootfs")
            if (not isinstance(layers, list) or not isinstance(rootfs, dict)
                    or rootfs.get("type") != "layers"
                    or not isinstance(rootfs.get("diff_ids"), list)
                    or len(rootfs["diff_ids"]) != len(layers)
                    or not all(isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
                               for digest in rootfs["diff_ids"])):
                raise ValueError("image layer metadata is malformed")
            # Docker rootfs.diff_ids bind each uncompressed layer's exact bytes.
            # Checking the config digest alone would allow an altered layer to
            # travel inside an otherwise correctly labelled customer package.
            # Hash in bounded chunks: a production image can exceed 1 GiB.
            for layer, expected_digest in zip(layers, rootfs["diff_ids"]):
                member = regular_member(layer)
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError(f"cannot read image layer: {layer}")
                digest = hashlib.sha256()
                total = 0
                with stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                        total += len(chunk)
                if total != member.size or "sha256:" + digest.hexdigest() != expected_digest:
                    raise ValueError("image layer content does not match rootfs diff_id")
            return labels, "sha256:" + config_hash
    except (tarfile.TarError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Docker image archive metadata: {exc}") from exc


def dependency_manifest(source: Path) -> tuple[str, list[dict[str, object]]]:
    matrix_path = source / MATRIX_FILE
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


def verify_source_checkout(source: Path, revision: str) -> None:
    """Use read-only Git commands; unrelated worktree changes are permitted."""
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(source), *args],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise ValueError("cannot verify the selected source Git checkout")
        return result.stdout.strip()

    if Path(git("rev-parse", "--show-toplevel")).resolve() != source:
        raise ValueError("selected source must be the Git checkout root")
    if git("rev-parse", "HEAD").lower() != revision.lower():
        raise ValueError("source checkout HEAD does not match the requested source revision")
    if git("status", "--porcelain=v1", "--untracked-files=all", "--", *ALLOWED_FILES, MATRIX_FILE):
        raise ValueError("source checkout has dirty package files or dependency matrix")


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
    """Publish the archive and its checksum only after full verification.

    A failed, interrupted, or oversized ZIP must never remain at the final
    customer-facing filename. Intermediate files use conspicuous .part names.
    """
    archive = package.parent / f"{package.name}.zip"
    checksum = archive.with_suffix(".zip.sha256")
    staging = archive.with_name(archive.name + ".part")
    staged_checksum = checksum.with_name(checksum.name + ".part")
    if any(path.exists() or path.is_symlink()
           for path in (archive, checksum, staging, staged_checksum)):
        raise ValueError("refusing to overwrite an existing customer ZIP, checksum, or partial archive")
    published = False
    try:
        with zipfile.ZipFile(staging, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as handle:
            for path in sorted(package.rglob("*")):
                if path.is_symlink():
                    raise ValueError(f"package contains a link: {path}")
                if path.is_file():
                    handle.write(path, path.relative_to(package.parent).as_posix())
        if staging.stat().st_size >= MAX_RELEASE_ASSET_BYTES:
            raise ValueError("customer ZIP must be under GitHub's 2 GiB asset limit; reduce the provider image before publication")
        digest = sha256(staging)
        write_utf8(staged_checksum, digest + "  " + archive.name + "\n")
        # Never expose a final ZIP while it is still being written. On any
        # publishing error, remove only artifacts created by this attempt.
        staging.rename(archive)
        published = True
        staged_checksum.rename(checksum)
        return archive
    except BaseException:
        for temporary in (staging, staged_checksum):
            temporary.unlink(missing_ok=True)
        # Never remove another invocation's existing archive on an early
        # error; only this attempt's successful publish can be rolled back.
        if published:
            archive.unlink(missing_ok=True)
        raise


def create_package(
    *,
    source: Path,
    output: Path,
    image_archive: Path,
    image_labels: dict,
    version: str,
    source_revision: str,
    gate_evidence: Path,
    provider_attestation: str,
) -> tuple[Path, Path, dict]:
    source = source.resolve()
    output = output.resolve()
    # Resolve() follows symlinks. Reject the supplied archive path first so
    # callers cannot bypass the regular-file input boundary with an alias.
    if image_archive.is_symlink():
        raise ValueError("a regular prebuilt image archive is required (symlink rejected)")
    image_archive = image_archive.resolve()
    if not HEX40.fullmatch(source_revision):
        raise ValueError("source revision must be a full 40-character commit SHA")
    if not SAFE_VERSION.fullmatch(version):
        raise ValueError("version contains unsupported characters")
    if not image_archive.is_file() or image_archive.is_symlink():
        raise ValueError("a regular prebuilt image archive is required")
    if source == output or output.is_relative_to(source):
        raise ValueError("output must be outside the source repository")
    if (not isinstance(image_labels, dict)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in image_labels.items())):
        raise ValueError("supplied image labels must be a string mapping")
    if image_labels.get("org.toefl-house.source-eol") != "lf-v1":
        raise ValueError("image lacks org.toefl-house.source-eol=lf-v1")
    if image_labels.get("org.toefl-house.source-revision") != source_revision:
        raise ValueError("image source revision does not match the requested package revision")
    if image_labels.get("org.toefl-house.release-version") != version:
        raise ValueError("image release version does not match the requested package version")
    qualification = load_gate_evidence(gate_evidence, source_revision)
    archive_labels, config_digest = archive_identity(image_archive, image_labels)
    verify_source_checkout(source, source_revision)
    # Reject incomplete source inputs before creating even the output directory.
    for relative in ALLOWED_FILES:
        origin = source / relative
        if not origin.is_file() or origin.is_symlink():
            raise ValueError(f"required package component is missing or linked: {relative}")
    matrix_hash, dependencies = dependency_manifest(source)

    package = output / f"TOEFL-House-ERP-Customer-{version}"
    if package.exists():
        raise ValueError(f"refusing to overwrite existing package: {package}")
    package.mkdir(parents=True)
    try:
        copy_allowlist(source, package)
        release = package / "product/release"
        release.mkdir(parents=True)
        packaged_gates = release / "ci-gates.json"
        shutil.copy2(gate_evidence, packaged_gates)
        if load_gate_evidence(packaged_gates, source_revision) != qualification:
            raise ValueError("CI gate evidence changed during customer package assembly")
        gate_evidence_hash = sha256(packaged_gates)
        write_utf8(release / "ci-gates.json.sha256", gate_evidence_hash + "  ci-gates.json\n")
        archive = release / "toefl-house-erp-app.tar"
        shutil.copy2(image_archive, archive)
        archive_hash = sha256(archive)
        checksum = release / "toefl-house-erp-app.tar.sha256"
        write_utf8(checksum, archive_hash + "  toefl-house-erp-app.tar\n")
        manifest = {
            "schema_version": 1,
            "product": "TOEFL House ERP",
            "version": version,
            "release_status": "TEST PACKAGE - NO REAL DATA",
            "production_authorization": "REJECT",
            "source_revision": source_revision,
            "image": {
                "tag": IMAGE_TAG,
                "config_digest": config_digest,
                "archive": "product/release/toefl-house-erp-app.tar",
                "sha256": archive_hash,
                "size_bytes": archive.stat().st_size,
                "labels": archive_labels,
            },
            "dependency_matrix_sha256": matrix_hash,
            "dependencies": dependencies,
            "qualification": {
                "scope": qualification["scope"],
                "evidence": "product/release/ci-gates.json",
                "sha256": gate_evidence_hash,
                "repository": qualification["repository"],
                "source_revision": qualification["source_revision"],
                "gates": qualification["gates"],
                "real_owner_windows": "NOT_VERIFIED",
            },
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

This folder is an engineering kit, not the final single-file customer delivery.
The provider must assemble the offline Setup EXE with signed Windows prerequisites
and the pinned database/cache images before customer handover.

1. Use the provider-supplied Setup EXE and follow its Windows setup dialogs.
2. For engineering inspection of this kit, double-click TOEFL House ERP.vbs.
3. Use Install on a genuinely new computer, then use Open / Start on later days.
4. Open the included Owner Handbook from the GUI, then use the Owner Readiness
   Guide and DAILY USE GUIDE.txt. They are acceptance instructions, not
   production approval.

Verify product/release/release-manifest.json and its checksum with the trusted
provider before use. The same folder contains ci-gates.json and its checksum:
these bind the four hosted engineering gate runs to this exact source revision.
They are not real Windows, Owner-machine, recovery, staff, or production approval.
The archive checksum detects corruption; the provider attestation/signature is
the identity check. Release status is TEST PACKAGE - NO REAL DATA and production
authorization is REJECT. Do not enter real student, payroll or financial data
until the owner gates are separately approved.
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
    parser.add_argument("--gate-evidence", type=Path, required=True,
                        help="passing exact-SHA receipt from verify_ci_gates.py --output")
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
            gate_evidence=args.gate_evidence,
            provider_attestation=args.provider_attestation,
        )
        print(json.dumps({
            "package": str(package),
            "archive": str(archive),
            "archive_sha256": sha256(archive),
            "image_archive_sha256": manifest["image"]["sha256"],
            "version": manifest["version"],
            "source_revision": manifest["source_revision"],
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"customer package creation failed safely: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
