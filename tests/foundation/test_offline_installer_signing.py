"""Fail-closed Windows EXE publisher identity and re-installation contracts.

These static checks support, but do not replace, real Authenticode signing,
Windows executable execution, code-signature trust and offline recovery UAT.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILDER = (ROOT / "tools/release/Build Customer Installer.ps1").read_text(encoding="utf-8")
SETUP = (ROOT / "tools/release/windows/CustomerSetup.cs").read_text(encoding="utf-8")


class OfflineInstallerSigningTests(unittest.TestCase):
    def test_unsigned_output_is_explicitly_test_only(self):
        self.assertIn("$manifest.production_authorization -cne 'REJECT'", BUILDER)
        self.assertIn("UNSIGNED TEST INSTALLER ONLY", BUILDER)
        self.assertIn("SigningCertificateThumbprint", BUILDER)
        self.assertIn("Set-AuthenticodeSignature", BUILDER)
        self.assertIn("Get-AuthenticodeSignature -LiteralPath $partial", BUILDER)
        self.assertIn("TimeStamperCertificate", BUILDER)
        self.assertIn("4294960000", BUILDER)
        self.assertLess(BUILDER.index("Set-AuthenticodeSignature"),
                        BUILDER.index("& $partial --verify-payload"))
        self.assertLess(BUILDER.index("& $partial --verify-payload"),
                        BUILDER.index("[IO.File]::Move($partial, $output)"))
        self.assertIn("The assembled Windows installer failed self-verification.", BUILDER)
        self.assertIn("SourceRevision", BUILDER)

    def test_existing_installer_never_reinitializes_a_site(self):
        existing = SETUP.split("if (Directory.Exists(target)) {", 1)[1].split(
            "Directory.CreateDirectory(parent);", 1)[0]
        self.assertIn("Launch(target, false);", existing)
        self.assertNotIn("Launch(target, true);", existing)
        self.assertIn("Launch(target, true);", SETUP)

    def test_archive_validation_runs_before_extracting_any_file(self):
        validator = SETUP.split("public static void ExtractPayload(", 1)[1]
        self.assertIn("MaxPayloadEntries", validator)
        self.assertIn("MaxUnpackedBytes - expanded", validator)
        self.assertIn("IsDeviceName(segment)", validator)
        self.assertIn("segment.TrimEnd(' ', '.') != segment", validator)
        self.assertLess(validator.index("foreach (ZipArchiveEntry entry in archive.Entries)"),
                        validator.index("entry.ExtractToFile(path)"))


if __name__ == "__main__":
    unittest.main()
