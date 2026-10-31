"""Provider export succeeds only for exact pinned Linux/amd64 runtime inputs."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.release.export_offline_runtime import export_runtime


class OfflineRuntimeExport(unittest.TestCase):
    def test_export_binds_archives_to_source_and_loaded_image_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compose = root / 'compose.yml'
            compose.write_text('services:\n  db:\n    image: mariadb@sha256:' + '1' * 64 +
                               '\n  cache:\n    image: redis@sha256:' + '2' * 64 + '\n')
            output = root / 'runtime'
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                if args[1] == 'save':
                    Path(args[3]).write_bytes(b'synthetic archive')

            identity = [{'Os': 'linux', 'Architecture': 'amd64',
                         'Config': {'Env': ['SYNTHETIC=yes']}, 'RootFS': {'Layers': ['layer']}}]
            with patch('tools.release.export_offline_runtime.subprocess.run', side_effect=run), patch(
                'tools.release.export_offline_runtime.subprocess.check_output', return_value=json.dumps(identity)
            ):
                export_runtime(compose, output, 'a' * 40)
            manifest = json.loads((output / 'offline-runtime.json').read_text())
            self.assertEqual(manifest['source_revision'], 'a' * 40)
            self.assertEqual(len(manifest['images']), 2)
            for image in manifest['images']:
                self.assertEqual(image['sha256'], hashlib.sha256(b'synthetic archive').hexdigest())
                self.assertEqual(image['config'], identity[0]['Config'])
            pulls = [call for call in calls if call[1] == 'pull']
            self.assertEqual(len(pulls), 2)
            self.assertTrue(all(call[2:4] == ['--platform', 'linux/amd64'] for call in pulls))

    def test_unpinned_source_refuses_before_docker_or_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compose = root / 'compose.yml'
            compose.write_text('services:\n  db:\n    image: mariadb:latest\n')
            with patch('tools.release.export_offline_runtime.subprocess.run') as run:
                with self.assertRaises(ValueError):
                    export_runtime(compose, root / 'output', 'a' * 40)
                run.assert_not_called()
            self.assertFalse((root / 'output').exists())

    def test_failed_second_image_export_leaves_no_partial_customer_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compose = root / "compose.yml"
            compose.write_text("services:\n  db:\n    image: mariadb@sha256:" +
                               "1" * 64 + "\n  cache:\n    image: redis@sha256:" +
                               "2" * 64 + "\n", encoding="utf-8")
            output = root / "release" / "runtime"
            identity = [{"Os": "linux", "Architecture": "amd64",
                         "Config": {}, "RootFS": {"Layers": ["sha256:synthetic"]}}]
            def fake_run(args, **kwargs):
                if args[1] == "save":
                    Path(args[3]).write_bytes(b"partial synthetic image")
                    if "cache" in args[3]:
                        raise OSError("synthetic second-archive write failure")
            with patch("tools.release.export_offline_runtime.subprocess.run",
                       side_effect=fake_run), patch(
                    "tools.release.export_offline_runtime.subprocess.check_output",
                    return_value=json.dumps(identity)):
                with self.assertRaisesRegex(OSError, "synthetic second-archive"):
                    export_runtime(compose, output, "a" * 40)
            self.assertFalse(output.exists())
            self.assertFalse(list(output.parent.glob(".offline-runtime-*")))
            # A later clean attempt can retry the exact same destination.
            with patch("tools.release.export_offline_runtime.subprocess.run",
                       side_effect=lambda args, **kwargs: (
                           Path(args[3]).write_bytes(b"complete")
                           if args[1] == "save" else None)), patch(
                    "tools.release.export_offline_runtime.subprocess.check_output",
                    return_value=json.dumps(identity)):
                export_runtime(compose, output, "a" * 40)
            self.assertEqual(len(list(output.glob("*.tar"))), 2)

    def test_broken_symlink_target_refuses_before_any_docker_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compose = root / "compose.yml"
            compose.write_text("services:\n  db:\n    image: mariadb@sha256:" +
                               "1" * 64 + "\n  cache:\n    image: redis@sha256:" +
                               "2" * 64 + "\n")
            output = root / "runtime"
            output.symlink_to(root / "nonexistent", target_is_directory=True)
            with patch("tools.release.export_offline_runtime.subprocess.run") as run:
                with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                    export_runtime(compose, output, "a" * 40)
                run.assert_not_called()
            self.assertTrue(output.is_symlink())

    def test_prerequisite_catalog_uses_fixed_official_sources_and_hashes(self):
        root = Path(__file__).resolve().parents[2]
        catalog = json.loads((root / 'tools/release/windows-prerequisites.json').read_text())
        self.assertTrue(catalog['wsl']['url'].startswith('https://github.com/microsoft/WSL/releases/download/'))
        self.assertTrue(catalog['docker']['url'].startswith('https://desktop.docker.com/win/main/amd64/'))
        for entry in (catalog['wsl'], catalog['docker']):
            self.assertRegex(entry['sha256'], r'^[a-f0-9]{64}$')
            self.assertNotIn('latest', entry['url'])
