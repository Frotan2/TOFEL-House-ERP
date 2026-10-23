"""Provider-side customer package identity and allowlist contracts."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from tools.release.create_customer_package import ALLOWED_FILES, MATRIX_FILE, create_package


ROOT = Path(__file__).resolve().parents[2]
IMAGE_TAG = "toefl-house-erp-app:local"


def image_archive_members(labels: dict) -> tuple[dict[str, bytes], str]:
    """A real Docker-save layout, including an uncompressed filesystem layer."""
    layer = io.BytesIO()
    with tarfile.open(fileobj=layer, mode="w") as archive:
        data = b"synthetic application\n"
        member = tarfile.TarInfo("application.txt")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    layer_bytes = layer.getvalue()
    config = json.dumps({
        "architecture": "amd64", "os": "linux", "config": {"Labels": labels},
        "rootfs": {"type": "layers", "diff_ids": ["sha256:" + hashlib.sha256(layer_bytes).hexdigest()]},
    }, sort_keys=True).encode()
    digest = hashlib.sha256(config).hexdigest()
    manifest = [{"Config": digest + ".json", "RepoTags": [IMAGE_TAG], "Layers": ["layer/layer.tar"]}]
    return {
        "manifest.json": json.dumps(manifest).encode(),
        digest + ".json": config,
        "layer/layer.tar": layer_bytes,
    }, "sha256:" + digest


def write_tar(path: Path, members: dict[str, bytes]) -> None:
    with tarfile.open(path, "w") as archive:
        for name, data in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))


def write_image_archive(path: Path, labels: dict) -> str:
    """Shared with the Windows fake-Docker workflow; return its config digest."""
    members, digest = image_archive_members(labels)
    write_tar(path, members)
    return digest


class CustomerPackageManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A committed, isolated source fixture keeps production HEAD/dirty-file
        # checks real without touching or depending on the developer's checkout.
        cls.source_temp = tempfile.TemporaryDirectory(prefix="customer-source-fixture-")
        cls.addClassCleanup(cls.source_temp.cleanup)
        cls.source_seed = Path(cls.source_temp.name) / "source"
        source_files = (*ALLOWED_FILES, MATRIX_FILE, "product/windows/Prepare Customer Package.ps1")
        for relative in source_files:
            target = cls.source_seed / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        for args in (("init", "-q"), ("config", "core.autocrlf", "false"), ("add", "."),
                     ("-c", "user.name=Synthetic fixture", "-c", "user.email=fixture@example.invalid",
                      "-c", "commit.gpgsign=false", "commit", "-qm", "Synthetic customer package inputs")):
            subprocess.run(["git", "-C", str(cls.source_seed), *args], env=env,
                           check=True, capture_output=True)
        cls.fixture_revision = subprocess.check_output(
            ["git", "-C", str(cls.source_seed), "rev-parse", "HEAD"], text=True).strip()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="customer-package-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.source = self.tmp / "source"
        shutil.copytree(self.source_seed, self.source)
        self.revision = self.fixture_revision
        self.version = "ci-test-20261023"
        self.image = self.tmp / "image.tar"
        self.labels = {
            "org.toefl-house.source-eol": "lf-v1",
            "org.toefl-house.source-revision": self.revision,
            "org.toefl-house.release-version": self.version,
        }
        self.members, self.config_digest = image_archive_members(self.labels)
        write_tar(self.image, self.members)

    def create(self, **overrides):
        args = dict(source=self.source, output=self.tmp / "out", image_archive=self.image,
                    image_labels=self.labels, version=self.version, source_revision=self.revision,
                    provider_attestation="synthetic-test-attestation")
        args.update(overrides)
        return create_package(**args)

    def assert_rejected_before_output(self, message="", **overrides):
        with self.assertRaisesRegex(ValueError, message):
            self.create(**overrides)
        self.assertFalse((self.tmp / "out").exists())

    def test_package_binds_image_source_and_dependency_matrix(self):
        package, archive, manifest = create_package(
            source=self.source,
            output=self.tmp / "out",
            image_archive=self.image,
            image_labels=self.labels,
            version=self.version,
            source_revision=self.revision,
            provider_attestation="synthetic-test-attestation",
        )
        release = package / "product" / "release"
        saved = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["source_revision"], self.revision)
        self.assertEqual(saved["version"], self.version)
        self.assertEqual(saved["image"]["sha256"], manifest["image"]["sha256"])
        self.assertEqual(saved["image"]["labels"], self.labels)
        self.assertEqual(saved["image"]["tag"], IMAGE_TAG)
        self.assertEqual(saved["image"]["config_digest"], self.config_digest)
        self.assertTrue(archive.is_file())
        self.assertTrue((release / "release-manifest.json.sha256").is_file())
        self.assertFalse((package / "product" / "data").exists())
        self.assertFalse((package / "apps").exists())

    def test_image_identity_mismatch_fails_before_package_creation(self):
        with self.assertRaisesRegex(ValueError, "source revision"):
            create_package(
                source=self.source,
                output=self.tmp / "out",
                image_archive=self.image,
                image_labels=self.labels,
                version=self.version,
                source_revision="b" * 40,
                provider_attestation="synthetic-test-attestation",
            )
        self.assertFalse((self.tmp / "out").exists())

    def test_embedded_labels_must_match_sidecar(self):
        for key, value in (
            ("org.toefl-house.source-revision", "b" * 40),
            ("org.toefl-house.release-version", "other-release"),
            ("org.toefl-house.source-eol", "wrong"),
            ("extra-label", "not-in-sidecar"),
        ):
            with self.subTest(key=key):
                write_image_archive(self.image, dict(self.labels, **{key: value}))
                self.assert_rejected_before_output("config labels")

    def test_matching_additional_labels_are_preserved(self):
        labels = dict(self.labels, publisher="synthetic provider")
        write_image_archive(self.image, labels)
        _, _, manifest = self.create(image_labels=labels)
        self.assertEqual(manifest["image"]["labels"], labels)

    def test_nonlocal_or_additional_tags_are_rejected(self):
        for tags in (["toefl-house-erp-app:ci"], ["toefl-house-erp-app:customer"], [],
                     [IMAGE_TAG, "unrelated:latest"]):
            with self.subTest(tags=tags):
                entry = json.loads(self.members["manifest.json"])
                entry[0]["RepoTags"] = tags
                write_tar(self.image, dict(self.members, **{"manifest.json": json.dumps(entry).encode()}))
                self.assert_rejected_before_output("tag")

    def test_missing_archive_members_are_rejected(self):
        for name in self.members:
            with self.subTest(name=name):
                write_tar(self.image, {k: v for k, v in self.members.items() if k != name})
                self.assert_rejected_before_output("missing")

    def test_malformed_manifest_is_rejected(self):
        entry = json.loads(self.members["manifest.json"])[0]
        malformed = [b"not JSON", b"{}", b"[]", b"[null]", json.dumps([entry, entry]).encode()]
        for key, value in (("Config", None), ("Config", "../config.json"), ("Layers", None), ("Layers", [None])):
            malformed.append(json.dumps([dict(entry, **{key: value})]).encode())
        for payload in malformed:
            with self.subTest(payload=payload):
                write_tar(self.image, dict(self.members, **{"manifest.json": payload}))
                self.assert_rejected_before_output()

    def test_malformed_config_is_rejected(self):
        for config in (None, [], {"config": None}, {"config": {"Labels": []}},
                       {"config": {"Labels": {"bad": 123}}}, {"config": {"Labels": self.labels}}):
            with self.subTest(config=config):
                payload = json.dumps(config).encode()
                name = hashlib.sha256(payload).hexdigest() + ".json"
                entry = json.loads(self.members["manifest.json"])
                entry[0]["Config"] = name
                members = {"manifest.json": json.dumps(entry).encode(), name: payload,
                           "layer/layer.tar": self.members["layer/layer.tar"]}
                write_tar(self.image, members)
                self.assert_rejected_before_output()

    def test_config_content_must_match_digest_filename(self):
        name = self.config_digest.removeprefix("sha256:") + ".json"
        write_tar(self.image, dict(self.members, **{name: self.members[name] + b" "}))
        self.assert_rejected_before_output("config filename")

    def test_oci_config_path_is_supported(self):
        old_name = self.config_digest.removeprefix("sha256:") + ".json"
        name = "blobs/sha256/" + self.config_digest.removeprefix("sha256:")
        entry = json.loads(self.members["manifest.json"])
        entry[0]["Config"] = name
        members = {k: v for k, v in self.members.items() if k != old_name}
        members[name] = self.members[old_name]
        members["manifest.json"] = json.dumps(entry).encode()
        write_tar(self.image, members)
        self.assertEqual(self.create()[2]["image"]["config_digest"], self.config_digest)

    def test_duplicate_or_linked_metadata_is_rejected(self):
        with tarfile.open(self.image, "a") as archive:
            duplicate = tarfile.TarInfo("manifest.json")
            duplicate.size = len(self.members["manifest.json"])
            archive.addfile(duplicate, io.BytesIO(self.members["manifest.json"]))
        self.assert_rejected_before_output("duplicate")
        with tarfile.open(self.image, "w") as archive:
            linked = tarfile.TarInfo("manifest.json")
            linked.type = tarfile.SYMTYPE
            linked.linkname = "elsewhere"
            archive.addfile(linked)
        self.assert_rejected_before_output("non-regular")

    def test_non_tar_archive_is_rejected(self):
        self.image.write_bytes(b"not a Docker image")
        self.assert_rejected_before_output("invalid Docker image")

    def test_missing_archive_is_rejected(self):
        self.image.unlink()
        self.assert_rejected_before_output("prebuilt image archive")

    def test_source_head_must_match_image_revision(self):
        labels = dict(self.labels, **{"org.toefl-house.source-revision": "b" * 40})
        write_image_archive(self.image, labels)
        self.assert_rejected_before_output("checkout HEAD", image_labels=labels, source_revision="b" * 40)

    def test_dirty_package_files_and_matrix_are_rejected(self):
        for relative in ("product/windows/TOEFL House ERP.ps1", MATRIX_FILE):
            with self.subTest(relative=relative):
                path = self.source / relative
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\n")
                    self.assert_rejected_before_output("dirty")
                finally:
                    path.write_bytes(original)

    def test_staged_package_changes_are_rejected(self):
        path = self.source / "product/windows/TOEFL House ERP.ps1"
        path.write_bytes(path.read_bytes() + b"\n")
        subprocess.run(["git", "-C", str(self.source), "add", "--", str(path)], check=True, capture_output=True)
        self.assert_rejected_before_output("dirty")

    def test_unrelated_dirty_files_do_not_block_packaging(self):
        (self.source / "unrelated-note.txt").write_text("unrelated local note", encoding="utf-8")
        self.assertEqual(self.create()[2]["source_revision"], self.revision)

    def run_verifier(self, package, *, loaded=False, inspect=None, docker_exit=0):
        release = package / "product/release"
        if inspect is None:
            saved = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
            inspect = {"Id": saved["image"]["config_digest"], "RepoTags": [IMAGE_TAG],
                       "Config": {"Labels": dict(self.labels)}}
        env = dict(os.environ, TH_TEST_VERIFY_SCRIPT=str(ROOT / "product/windows/Verify Package Image.ps1"),
                   TH_TEST_RELEASE=str(release), TH_TEST_DOCKER_EXIT=str(docker_exit),
                   TH_TEST_INSPECT=json.dumps(inspect) if not isinstance(inspect, str) else inspect)
        command = r"""
function docker {
    if ($args[0] -ne 'image' -or $args[1] -ne 'inspect' -or $args[2] -ne 'toefl-house-erp-app:local') {
        throw 'Unexpected Docker command in verifier test'
    }
    $global:LASTEXITCODE = [int]$env:TH_TEST_DOCKER_EXIT
    Write-Output $env:TH_TEST_INSPECT
}
& $env:TH_TEST_VERIFY_SCRIPT -Archive ($env:TH_TEST_RELEASE + '/toefl-house-erp-app.tar') -Checksum ($env:TH_TEST_RELEASE + '/toefl-house-erp-app.tar.sha256') -Manifest ($env:TH_TEST_RELEASE + '/release-manifest.json')
exit $LASTEXITCODE
"""
        if loaded:
            command = command.replace("\nexit $LASTEXITCODE", " -VerifyLoadedImage\nexit $LASTEXITCODE")
        return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-Command", command], env=env, capture_output=True, text=True, timeout=30)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell verifier")
    def test_windows_verifier_accepts_archive_and_loaded_identity(self):
        package, _, _ = self.create()
        for loaded in (False, True):
            with self.subTest(loaded=loaded):
                result = self.run_verifier(package, loaded=loaded)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Docker 29/containerd can report a manifest digest as .Id. It need not
        # equal the config digest already checked against the archive bytes.
        result = self.run_verifier(package, loaded=True, inspect={
            "Id": "sha256:" + "c" * 64, "RepoTags": [IMAGE_TAG], "Config": {"Labels": self.labels}})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell verifier")
    def test_windows_verifier_binds_config_digest_to_archive(self):
        package, _, _ = self.create()
        manifest = package / "product/release/release-manifest.json"
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        saved["image"]["config_digest"] = "sha256:" + "c" * 64
        manifest.write_text(json.dumps(saved), encoding="utf-8")
        manifest.with_suffix(".json.sha256").write_text(
            hashlib.sha256(manifest.read_bytes()).hexdigest() + "  release-manifest.json\n", encoding="utf-8")
        result = self.run_verifier(package)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("archive config", result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell verifier")
    def test_windows_verifier_rejects_unchecked_manifest_before_json_parse(self):
        package, _, _ = self.create()
        manifest = package / "product/release/release-manifest.json"
        manifest.write_bytes(b"this is invalid JSON, with a stale checksum")
        for loaded in (False, True):
            with self.subTest(loaded=loaded):
                result = self.run_verifier_raw(package, loaded=loaded)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("manifest failed its SHA-256", result.stderr)

    def run_verifier_raw(self, package, *, loaded=False):
        # Avoid parsing the deliberately damaged manifest in the fixture helper.
        return self.run_verifier(package, loaded=loaded, inspect={})

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell verifier")
    def test_windows_verifier_requires_valid_manifest_checksum(self):
        package, _, _ = self.create()
        checksum = package / "product/release/release-manifest.json.sha256"
        for content in (None, "not-a-digest", "0" * 64, ("0" * 64 + "\n") * 2):
            with self.subTest(content=content):
                if content is None:
                    checksum.unlink()
                else:
                    checksum.write_text(content, encoding="utf-8")
                result = self.run_verifier(package)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("manifest", result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell verifier")
    def test_windows_verifier_rejects_loaded_identity_mismatches(self):
        package, _, manifest = self.create()
        valid = {"Id": manifest["image"]["config_digest"], "RepoTags": [IMAGE_TAG],
                 "Config": {"Labels": dict(self.labels)}}
        bad = [dict(valid, RepoTags=["toefl-house-erp-app:ci"]),
               {}, [], "not-json"]
        for key, value in (("org.toefl-house.source-revision", "b" * 40),
                           ("org.toefl-house.release-version", "wrong"), ("org.toefl-house.source-eol", "wrong")):
            bad.append(dict(valid, Config={"Labels": dict(self.labels, **{key: value})}))
        for inspect in bad:
            with self.subTest(inspect=inspect):
                result = self.run_verifier(package, loaded=True, inspect=inspect)
                self.assertNotEqual(result.returncode, 0, result.stdout)
        result = self.run_verifier(package, loaded=True, docker_exit=1)
        self.assertNotEqual(result.returncode, 0)

    def run_windows_preparer(self, revision):
        labels = dict(self.labels, **{"org.toefl-house.source-revision": revision})
        env = dict(os.environ, TH_TEST_PREPARER=str(self.source / "product/windows/Prepare Customer Package.ps1"),
                   TH_TEST_DESTINATION=str(self.tmp / "out"), TH_TEST_REVISION=revision, TH_TEST_VERSION=self.version,
                   TH_TEST_INSPECT=json.dumps({"Id": "sha256:" + "c" * 64, "RepoTags": [IMAGE_TAG],
                                               "Config": {"Labels": labels}}))
        command = r"""
function docker {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'info') { return }
    if ($args[0] -eq 'image' -and $args[1] -eq 'inspect') { Write-Output $env:TH_TEST_INSPECT; return }
    throw 'Source validation must reject before Docker export'
}
& $env:TH_TEST_PREPARER -Destination $env:TH_TEST_DESTINATION -Version $env:TH_TEST_VERSION -SourceRevision $env:TH_TEST_REVISION
exit $LASTEXITCODE
"""
        return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-Command", command], env=env, capture_output=True, text=True, timeout=30)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell provider")
    def test_windows_preparer_rejects_wrong_head_before_output(self):
        result = self.run_windows_preparer("b" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checkout HEAD", result.stderr)
        self.assertFalse((self.tmp / "out").exists())

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell provider")
    def test_windows_preparer_rejects_dirty_inputs_before_output(self):
        for relative in ("product/windows/TOEFL House ERP.ps1", MATRIX_FILE):
            with self.subTest(relative=relative):
                path = self.source / relative
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\n")
                    result = self.run_windows_preparer(self.revision)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("dirty package files", result.stderr)
                    self.assertFalse((self.tmp / "out").exists())
                finally:
                    path.write_bytes(original)

    def test_installer_checks_loaded_identity_before_compose(self):
        install = (ROOT / "product/windows/Install TOEFL House ERP.cmd").read_text(encoding="utf-8")
        self.assertLess(install.index("docker load -i"), install.index("-VerifyLoadedImage"))
        self.assertLess(install.index("-VerifyLoadedImage"), install.index("docker compose up -d --no-build"))


if __name__ == "__main__":
    unittest.main()
