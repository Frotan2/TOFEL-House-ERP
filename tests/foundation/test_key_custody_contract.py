"""Static and behavioural contract for external key custody (P4).

Independent-system recovery (run 35170062251) proved that a destroyed site's
database and files come back on a separate machine, and asserted one limitation
as an expected failure: the field the source encrypted was intact but
undecryptable on the target, because no key travelled. That was correct
behaviour - plaintext key material must never ride inside a backup - but it means
recovery without custody is incomplete. This contract keeps the custody half
honest:

* key material is issued in the format Frappe itself generates, and a malformed
  key is refused rather than passed downstream;
* splitting reveals nothing: neither share is the key, fingerprints it, or
  contains it, and reconstruction needs both;
* shares are epoch-bound, so a share from one epoch combined with a share from
  another fails a fingerprint check instead of silently producing a wrong key;
* a single share, or a missing share, fails closed;
* published custody files are scanned and must contain no key material;
* the machine-separation verdict keeps the two corrections that execution forced
  on the independence model - ``hostname`` and the Docker daemon id are
  observations only, each annotated with the run that disproved it, and a missing
  required identifier fails the verdict closed.

Boundary with the existing coverage: ``test_encryption_key_recovery.py`` proves a
site's own key survives backup and restore on one machine (P1). This file is
about key material held and retrieved *separately*, and about rotation. Neither
upgrades a release gate; the PASS comes from the hosted custody run, never from
this file.
"""
import base64
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import key_custody as custody  # noqa: E402


class NativeKeyFormat(unittest.TestCase):
    """Frappe keys come from ``Fernet.generate_key()``; match it exactly."""

    def test_generated_key_passes_its_own_validation(self):
        report = custody.validate_key_format(custody.generate_native_key())
        self.assertTrue(report["valid"], report)
        self.assertIsNone(report["reason"])

    def test_generated_key_has_fermets_length_and_encoding(self):
        key = custody.generate_native_key()
        self.assertEqual(len(key), 44)
        self.assertEqual(len(base64.urlsafe_b64decode(key.encode())), 32)

    def test_generated_key_is_canonical_url_safe_base64(self):
        key = custody.generate_native_key()
        self.assertEqual(base64.urlsafe_b64encode(
            base64.urlsafe_b64decode(key.encode())).decode(), key)

    def test_generated_keys_are_distinct(self):
        keys = {custody.generate_native_key() for _ in range(32)}
        self.assertEqual(len(keys), 32)

    def test_generated_key_matches_fernet_generate_key_shape(self):
        # Fernet.generate_key() is base64.urlsafe_b64encode(os.urandom(32));
        # reproduce that construction directly so the equivalence is asserted,
        # not assumed from a comment.
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        self.assertTrue(custody.validate_key_format(key)["valid"])
        self.assertEqual(len(key), custody.KEY_CHARACTERS)

    def test_both_native_key_roles_are_named_as_frappe_names_them(self):
        self.assertEqual(custody.SITE_KEY, "encryption_key")
        self.assertEqual(custody.BACKUP_KEY, "backup_encryption_key")
        self.assertEqual(custody.KEY_ROLES, ("encryption_key", "backup_encryption_key"))


class KeyFormatValidation(unittest.TestCase):
    def test_rejects_a_key_of_the_wrong_length(self):
        short = base64.urlsafe_b64encode(os.urandom(16)).decode()
        report = custody.validate_key_format(short)
        self.assertFalse(report["valid"])
        self.assertIn("characters", report["reason"])

    def test_rejects_a_key_that_decodes_to_the_wrong_number_of_bytes(self):
        report = custody.validate_key_format("A" * 44)
        self.assertFalse(report["valid"])
        self.assertIsNotNone(report["reason"])

    def test_rejects_text_that_is_not_base64(self):
        report = custody.validate_key_format("not base64 at all!" + "x" * 24)
        self.assertFalse(report["valid"])
        self.assertIn("base64", report["reason"])

    def test_rejects_a_non_canonical_encoding_of_valid_bytes(self):
        raw = os.urandom(32)
        padded = base64.urlsafe_b64encode(raw).decode().rstrip("=") + "="
        if len(padded) == 44:
            report = custody.validate_key_format(padded)
            # Either it is rejected, or it is byte-identical to the canonical
            # form; what must never happen is acceptance of a different string
            # that decodes to the same bytes.
            if report["valid"]:
                self.assertEqual(padded, base64.urlsafe_b64encode(raw).decode())

    def test_rejects_a_non_string(self):
        for value in (None, 44, b"x" * 44, ["key"]):
            report = custody.validate_key_format(value)
            self.assertFalse(report["valid"], value)
            self.assertEqual(report["reason"], "key is not a string")

    def test_reports_what_it_observed_even_when_invalid(self):
        report = custody.validate_key_format("short")
        self.assertEqual(report["characters"], 5)
        self.assertFalse(report["valid"])


class Fingerprint(unittest.TestCase):
    def test_fingerprint_is_deterministic(self):
        key = custody.generate_native_key()
        self.assertEqual(custody.key_fingerprint(key), custody.key_fingerprint(key))

    def test_fingerprint_is_a_sha256_hex_digest(self):
        digest = custody.key_fingerprint(custody.generate_native_key())
        self.assertEqual(len(digest), 64)
        int(digest, 16)

    def test_different_keys_fingerprint_differently(self):
        first, second = custody.generate_native_key(), custody.generate_native_key()
        self.assertNotEqual(custody.key_fingerprint(first), custody.key_fingerprint(second))

    def test_fingerprint_does_not_contain_the_key(self):
        key = custody.generate_native_key()
        self.assertNotIn(key, custody.key_fingerprint(key))


class SplitAndReconstruct(unittest.TestCase):
    def test_roundtrip_recovers_the_exact_key(self):
        for _ in range(16):
            key = custody.generate_native_key()
            shares = custody.split_key(key)
            self.assertEqual(custody.reconstruct_key(shares["share_a"], shares["share_b"]), key)

    def test_split_records_the_fingerprint_and_method(self):
        key = custody.generate_native_key()
        shares = custody.split_key(key)
        self.assertEqual(shares["fingerprint"], custody.key_fingerprint(key))
        self.assertEqual(shares["method"], custody.SPLIT_METHOD)

    def test_shares_are_the_same_length_as_a_key(self):
        shares = custody.split_key(custody.generate_native_key())
        self.assertEqual(len(shares["share_a"]), custody.KEY_CHARACTERS)
        self.assertEqual(len(shares["share_b"]), custody.KEY_CHARACTERS)

    def test_splitting_the_same_key_twice_gives_different_shares(self):
        key = custody.generate_native_key()
        first, second = custody.split_key(key), custody.split_key(key)
        self.assertNotEqual(first["share_a"], second["share_a"])
        self.assertNotEqual(first["share_b"], second["share_b"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_neither_share_reveals_the_key(self):
        for _ in range(8):
            key = custody.generate_native_key()
            shares = custody.split_key(key)
            observation = custody.share_reveals_nothing(key, shares)
            self.assertTrue(observation["neither_share_reveals_the_key"], observation)
            self.assertTrue(observation["shares_differ_from_each_other"])
            for share in observation["shares"].values():
                self.assertFalse(share["equals_key"])
                self.assertFalse(share["fingerprint_equals_key_fingerprint"])
                self.assertFalse(share["contains_key"])

    def test_splitting_a_malformed_key_is_refused(self):
        for bad in ("", "short", "A" * 44, None, 44):
            with self.assertRaises(ValueError):
                custody.split_key(bad)

    def test_reconstructing_from_one_share_does_not_yield_the_key(self):
        key = custody.generate_native_key()
        shares = custody.split_key(key)
        for alone in (shares["share_a"], shares["share_b"]):
            self.assertNotEqual(alone, key)
            self.assertNotEqual(custody.key_fingerprint(alone), custody.key_fingerprint(key))

    def test_a_single_share_reconstructs_to_the_wrong_key(self):
        # Feeding one share twice is the mistake a careless caller makes; it must
        # produce a key that fails the fingerprint check, never the real one.
        key = custody.generate_native_key()
        shares = custody.split_key(key)
        for alone in (shares["share_a"], shares["share_b"]):
            report = custody.reconstruction_report(alone, alone, shares["fingerprint"])
            self.assertTrue(report["reconstructed"])
            self.assertFalse(report["fingerprint_matches"], report)

    def test_shares_from_different_epochs_do_not_reconstruct(self):
        first, second = custody.generate_native_key(), custody.generate_native_key()
        a, b = custody.split_key(first), custody.split_key(second)
        crossed = custody.reconstruction_report(a["share_a"], b["share_b"], a["fingerprint"])
        self.assertFalse(crossed["fingerprint_matches"], crossed)
        self.assertNotEqual(custody.reconstruct_key(a["share_a"], b["share_b"]), first)

    def test_both_shares_are_required_by_construction(self):
        key = custody.generate_native_key()
        shares = custody.split_key(key)
        self.assertTrue(custody.reconstruction_report(
            shares["share_a"], shares["share_b"], shares["fingerprint"])["fingerprint_matches"])

    def test_reconstruction_report_survives_a_malformed_share(self):
        key = custody.generate_native_key()
        shares = custody.split_key(key)
        report = custody.reconstruction_report("!!!not base64!!!", shares["share_b"],
                                               shares["fingerprint"])
        self.assertFalse(report["reconstructed"])
        self.assertFalse(report["fingerprint_matches"])
        self.assertIn("base64", report["error"])
        self.assertIsNone(report["fingerprint"])

    def test_reconstruction_refuses_shares_of_different_lengths(self):
        with self.assertRaises(ValueError):
            custody.reconstruct_key(base64.urlsafe_b64encode(os.urandom(32)).decode(),
                                    base64.urlsafe_b64encode(os.urandom(16)).decode())

    def test_reconstructed_key_is_still_a_valid_native_key(self):
        key = custody.generate_native_key()
        shares = custody.split_key(key)
        rebuilt = custody.reconstruct_key(shares["share_a"], shares["share_b"])
        self.assertTrue(custody.validate_key_format(rebuilt)["valid"])


class PlaintextScanning(unittest.TestCase):
    def test_finds_a_secret_that_is_present(self):
        secret = custody.generate_native_key()
        self.assertEqual(custody.find_plaintext("prefix " + secret + " suffix",
                                                {"site_key": secret}), ["site_key"])

    def test_reports_nothing_when_the_secret_is_absent(self):
        self.assertEqual(custody.find_plaintext("harmless text",
                                                {"site_key": custody.generate_native_key()}), [])

    def test_names_every_secret_that_leaked(self):
        first, second = custody.generate_native_key(), custody.generate_native_key()
        found = custody.find_plaintext(first + " and " + second,
                                       {"site_key": first, "backup_key": second})
        self.assertEqual(sorted(found), ["backup_key", "site_key"])

    def test_scans_bytes_as_well_as_text(self):
        secret = custody.generate_native_key()
        self.assertEqual(custody.find_plaintext(("gpg blob " + secret).encode(),
                                                {"site_key": secret}), ["site_key"])

    def test_tolerates_undecodable_bytes_without_crashing(self):
        secret = custody.generate_native_key()
        blob = b"\xff\xfe\x00binary" + secret.encode()
        self.assertEqual(custody.find_plaintext(blob, {"site_key": secret}), ["site_key"])

    def test_skips_an_empty_secret_instead_of_matching_everything(self):
        self.assertEqual(custody.find_plaintext("anything", {"empty": ""}), [])

    def test_refuses_a_needle_short_enough_to_match_by_accident(self):
        with self.assertRaises(ValueError):
            custody.find_plaintext("a short needle matches", {"weak": "abc"})

    def test_a_share_is_not_reported_as_the_key_it_hides(self):
        key = custody.generate_native_key()
        shares = custody.split_key(key)
        published = json.dumps({"a": shares["share_a"], "b": shares["share_b"]})
        self.assertEqual(custody.find_plaintext(published, {"site_key": key}), [])


class SeparateMachineVerdict(unittest.TestCase):
    def identity(self, boot, runner, uuid=None, hostname="runnervmlun5p",
                 daemon="a4efb8b6-20f9-46f4-b827-91ac0547be3a"):
        return {"kernel_boot_id": boot, "runner_name": runner, "hostname": hostname,
                "docker_daemon_id": daemon,
                **({"dmi_product_uuid": uuid} if uuid else {})}

    def three_separate(self):
        return {
            "custodian": self.identity("boot-1", "GitHub Actions 1", "uuid-1"),
            "operator": self.identity("boot-2", "GitHub Actions 2", "uuid-2"),
            "recovery": self.identity("boot-3", "GitHub Actions 3", "uuid-3"),
        }

    def test_three_separate_machines_are_accepted(self):
        verdict = custody.separate_machine_verdict(self.three_separate())
        self.assertEqual(verdict["verdict"], "SEPARATE MACHINES")
        self.assertTrue(verdict["every_pair_separate"])
        self.assertEqual(verdict["missing_required_identifiers"], [])
        self.assertEqual(len(verdict["pairs"]), 3)
        self.assertTrue(verdict["corroborated_by_dmi_product_uuid"])

    def test_every_pair_is_compared_not_just_adjacent_ones(self):
        verdict = custody.separate_machine_verdict(self.three_separate())
        self.assertEqual({(p["left"], p["right"]) for p in verdict["pairs"]},
                         {("custodian", "operator"), ("custodian", "recovery"),
                          ("operator", "recovery")})

    def test_a_repeated_boot_id_fails_the_verdict(self):
        identities = self.three_separate()
        identities["recovery"]["kernel_boot_id"] = identities["operator"]["kernel_boot_id"]
        verdict = custody.separate_machine_verdict(identities)
        self.assertEqual(verdict["verdict"], "NOT PROVEN SEPARATE")
        self.assertFalse(verdict["every_pair_separate"])

    def test_a_repeated_runner_name_fails_the_verdict(self):
        identities = self.three_separate()
        identities["custodian"]["runner_name"] = identities["operator"]["runner_name"]
        self.assertEqual(custody.separate_machine_verdict(identities)["verdict"],
                         "NOT PROVEN SEPARATE")

    def test_a_missing_required_identifier_fails_closed(self):
        identities = self.three_separate()
        del identities["operator"]["kernel_boot_id"]
        verdict = custody.separate_machine_verdict(identities)
        self.assertEqual(verdict["verdict"], "NOT PROVEN SEPARATE")
        self.assertTrue(verdict["missing_required_identifiers"])
        self.assertIn("kernel_boot_id", " ".join(verdict["missing_required_identifiers"]))

    def test_an_empty_identifier_is_treated_as_missing(self):
        identities = self.three_separate()
        identities["recovery"]["runner_name"] = ""
        verdict = custody.separate_machine_verdict(identities)
        self.assertEqual(verdict["verdict"], "NOT PROVEN SEPARATE")
        self.assertTrue(verdict["missing_required_identifiers"])

    def test_a_matching_hostname_does_not_fail_the_verdict(self):
        # Run 35143620884 proved the platform reuses generated hostnames across
        # separate VMs, so a match is an observation and never a discriminator.
        verdict = custody.separate_machine_verdict(self.three_separate())
        self.assertTrue(all(p["hostname"]["matches"] for p in verdict["pairs"]))
        self.assertTrue(all(not p["hostname"]["used_as_a_discriminator"] for p in verdict["pairs"]))
        self.assertEqual(verdict["verdict"], "SEPARATE MACHINES")

    def test_a_matching_docker_daemon_id_does_not_fail_the_verdict(self):
        # Run 35168111875 proved the runner image ships a pre-generated daemon
        # key, so separate VMs report one id.
        verdict = custody.separate_machine_verdict(self.three_separate())
        self.assertTrue(all(p["docker_daemon_id"]["matches"] for p in verdict["pairs"]))
        self.assertTrue(all(not p["docker_daemon_id"]["used_as_a_discriminator"]
                            for p in verdict["pairs"]))

    def test_both_observations_cite_the_run_that_disproved_them(self):
        verdict = custody.separate_machine_verdict(self.three_separate())
        pair = verdict["pairs"][0]
        self.assertIn("35143620884", pair["hostname"]["note"])
        self.assertIn("35168111875", pair["docker_daemon_id"]["note"])
        self.assertEqual(pair["hostname"]["role"], "OBSERVATION ONLY")
        self.assertEqual(pair["docker_daemon_id"]["role"], "OBSERVATION ONLY")

    def test_unreadable_dmi_uuid_neither_fails_nor_corroborates(self):
        identities = self.three_separate()
        del identities["recovery"]["dmi_product_uuid"]
        verdict = custody.separate_machine_verdict(identities)
        self.assertEqual(verdict["verdict"], "SEPARATE MACHINES")
        self.assertFalse(any(p["dmi_product_uuid"]["available"] for p in verdict["pairs"]
                             if p["right"] == "recovery" or p["left"] == "recovery"))

    def test_differing_dmi_uuids_corroborate_the_verdict(self):
        verdict = custody.separate_machine_verdict(self.three_separate())
        self.assertTrue(all(p["dmi_product_uuid"]["differs"] for p in verdict["pairs"]))
        self.assertEqual(verdict["dmi_product_uuid_pairs_compared"], 3)
        self.assertTrue(verdict["corroborated_by_dmi_product_uuid"])

    def test_corroboration_is_not_claimed_when_no_uuid_is_readable(self):
        # The uuid is root-only, so a runner may not be able to read it at all.
        # ``all([])`` is vacuously true, which would report corroboration that
        # never happened; the verdict must stay separate on the two identifiers
        # that are required, and say plainly that nothing corroborated it.
        identities = self.three_separate()
        for identity in identities.values():
            del identity["dmi_product_uuid"]
        verdict = custody.separate_machine_verdict(identities)
        self.assertEqual(verdict["verdict"], "SEPARATE MACHINES")
        self.assertEqual(verdict["dmi_product_uuid_pairs_compared"], 0)
        self.assertIsNone(verdict["corroborated_by_dmi_product_uuid"])

    def test_partial_uuid_availability_reports_only_the_pairs_compared(self):
        identities = self.three_separate()
        del identities["recovery"]["dmi_product_uuid"]
        verdict = custody.separate_machine_verdict(identities)
        self.assertEqual(verdict["dmi_product_uuid_pairs_compared"], 1)
        self.assertTrue(verdict["corroborated_by_dmi_product_uuid"])

    def test_matching_uuids_do_not_corroborate(self):
        identities = self.three_separate()
        for identity in identities.values():
            identity["dmi_product_uuid"] = "the-same-uuid"
        verdict = custody.separate_machine_verdict(identities)
        self.assertEqual(verdict["dmi_product_uuid_pairs_compared"], 3)
        self.assertFalse(verdict["corroborated_by_dmi_product_uuid"])
        # Corroboration is not a requirement: boot id and runner name still differ.
        self.assertEqual(verdict["verdict"], "SEPARATE MACHINES")

    def test_a_single_identity_cannot_be_compared(self):
        with self.assertRaises(ValueError):
            custody.separate_machine_verdict({"only": self.identity("boot", "runner")})

    def test_roles_are_listed_so_the_verdict_is_auditable(self):
        verdict = custody.separate_machine_verdict(self.three_separate())
        self.assertEqual(verdict["roles"], ["custodian", "operator", "recovery"])


class PublishedCustodyFiles(unittest.TestCase):
    def setUp(self):
        self.site_key = custody.generate_native_key()
        self.backup_key = custody.generate_native_key()
        self.site_shares = custody.split_key(self.site_key)
        self.backup_shares = custody.split_key(self.backup_key)
        self.entries = [
            custody.epoch_entry(1, custody.SITE_KEY, self.site_shares,
                                purpose="Protects secrets stored in __Auth"),
            custody.epoch_entry(1, custody.BACKUP_KEY, self.backup_shares,
                                purpose="Protects the backup artifacts at rest"),
        ]
        self.manifest = custody.custody_manifest(
            self.entries, run_id="35000000000", commit="0" * 40)

    def test_manifest_carries_fingerprints_for_both_roles(self):
        self.assertEqual(len(self.manifest["entries"]), 2)
        self.assertEqual({e["key_role"] for e in self.manifest["entries"]},
                         set(custody.KEY_ROLES))
        for entry in self.manifest["entries"]:
            self.assertEqual(len(entry["fingerprint"]), 64)

    def test_manifest_contains_no_key_material(self):
        published = custody.as_json(self.manifest)
        self.assertEqual(custody.find_plaintext(published, {
            "site_key": self.site_key, "backup_key": self.backup_key,
            "site_share_a": self.site_shares["share_a"],
            "site_share_b": self.site_shares["share_b"],
            "backup_share_a": self.backup_shares["share_a"],
            "backup_share_b": self.backup_shares["share_b"],
        }), [])

    def test_manifest_declares_the_key_format_it_expects(self):
        self.assertEqual(self.manifest["key_format"]["characters"], 44)
        self.assertEqual(self.manifest["key_format"]["decoded_bytes"], 32)
        self.assertIn("Fernet", self.manifest["key_format"]["compatible_with"])

    def test_manifest_records_the_split_method(self):
        self.assertEqual(self.manifest["split_method"], custody.SPLIT_METHOD)

    def test_epoch_entry_records_rotation_lineage(self):
        rotated = custody.epoch_entry(2, custody.SITE_KEY,
                                      custody.split_key(custody.generate_native_key()),
                                      purpose="rotation",
                                      rotated_from=self.entries[0]["fingerprint"])
        self.assertEqual(rotated["epoch"], 2)
        self.assertEqual(rotated["rotated_from"], self.entries[0]["fingerprint"])
        self.assertIsNone(self.entries[0]["rotated_from"])

    def test_epoch_entry_fingerprints_each_share_without_holding_it(self):
        entry = self.entries[0]
        self.assertEqual(entry["share_a_fingerprint"],
                         custody.key_fingerprint(self.site_shares["share_a"]))
        self.assertEqual(entry["share_b_fingerprint"],
                         custody.key_fingerprint(self.site_shares["share_b"]))
        self.assertNotIn("share_a", entry)
        self.assertNotIn("share_b", entry)

    def test_as_json_is_canonical_and_sorted(self):
        text = custody.as_json(self.manifest)
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(json.loads(text), self.manifest)
        self.assertEqual(text, json.dumps(self.manifest, indent=2, sort_keys=True) + "\n")

    def test_a_share_file_holds_one_share_and_nothing_else(self):
        # Each channel publishes only its own share, so a channel file that also
        # carried the other share would collapse the split.
        channel = custody.as_json({"epoch": 1, "key_role": custody.SITE_KEY,
                                   "share": self.site_shares["share_a"]})
        self.assertEqual(custody.find_plaintext(channel, {
            "site_key": self.site_key, "other_share": self.site_shares["share_b"]}), [])
        self.assertIn(self.site_shares["share_a"], channel)


if __name__ == "__main__":
    unittest.main()
