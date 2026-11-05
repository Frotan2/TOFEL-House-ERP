"""Static boundaries for the isolated Oracle ARM64 staging target."""
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLOUD = ROOT / "product/oracle"


class OracleCloudContract(unittest.TestCase):
    def test_cloud_compose_is_separate_from_windows_state_and_digest_pinned(self):
        compose = (CLOUD / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("./product/data", compose)
        self.assertIn("toefl-house-cloud-staging", compose)
        self.assertIn("./data/sites:/home/frappe/bench/sites", compose)
        self.assertIn("db-data:/var/lib/mysql", compose)
        self.assertNotIn("container_name:", compose)
        self.assertGreaterEqual(compose.count("platform: linux/arm64"), 8)
        self.assertEqual(len(re.findall(r"^    image: .*@sha256:[0-9a-f]{64}$", compose, re.M)), 4)
        self.assertRegex(compose, r"image: \*app-image")
        self.assertIn("@sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5", compose)

    def test_only_reverse_proxy_publishes_public_ports(self):
        compose = (CLOUD / "docker-compose.yml").read_text(encoding="utf-8")
        services = compose.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]
        published = re.findall(r"^\s+- \"([0-9]+:[0-9]+(?:/udp)?)\"$", services, re.M)
        self.assertEqual(published, ["80:80", "443:443", "443:443/udp"])
        for service in ("db", "redis-queue", "redis-cache", "web", "socketio"):
            block = re.search(rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)", services)
            self.assertIsNotNone(block, service)
            self.assertNotRegex(block.group(1), r"(?m)^    ports:")

    def test_tls_uses_shortlived_public_acme_profile_and_same_origin_proxy(self):
        caddy = (CLOUD / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn("admin off", caddy)
        self.assertIn("profile shortlived", caddy)
        self.assertIn("reverse_proxy web:8000", caddy)
        self.assertNotIn("http://", caddy)
        compose = (CLOUD / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('"80:80"', compose)
        self.assertIn('"443:443"', compose)
        self.assertIn("Strict-Transport-Security", caddy)

    def test_arm64_workflow_uses_native_runner_and_verifies_official_node_pin(self):
        workflow = (ROOT / ".github/workflows/oracle-arm64-build.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-24.04-arm", workflow)
        self.assertIn('test "$(uname -m)" = aarch64', workflow)
        self.assertIn("SHASUMS256.txt", workflow)
        self.assertIn("docker buildx build --platform linux/arm64", workflow)
        self.assertIn("caddy:2.11.7-alpine@sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5", workflow)
        self.assertIn("Node archive digest does not match", workflow)
        self.assertNotIn("qemu-user-static", workflow.lower())

    def test_owner_cloud_direction_does_not_authorize_production_or_windows_changes(self):
        decisions = json.loads((ROOT / "docs/owner-decisions.json").read_text(encoding="utf-8"))
        cloud = decisions["owner_policy_addenda_2026_11_04_cloud_direction"]
        self.assertEqual(cloud["status"], "OWNER_CONFIRMED_CLOUD_STAGING_DIRECTION_NOT_PRODUCTION_AUTHORIZATION")
        self.assertIn("Oracle Cloud Infrastructure", cloud["scope"]["provider"])
        self.assertIn("synthetic", cloud["authorizes"][1].lower())
        self.assertTrue(any("Windows" in item for item in cloud["not_authorized"]))
        self.assertEqual(cloud["production_authorization"], "REJECT until every applicable release gate is objectively proven and explicit production authorization is separately recorded.")


if __name__ == "__main__":
    unittest.main()
