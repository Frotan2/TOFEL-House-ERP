"""Inspect an OCI tenancy's home-region A1 capacity from authenticated Cloud Shell."""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SHAPE = "VM.Standard.A1.Flex"
CONFIG = {"ocpus": 2, "memoryInGBs": 12}


def query(*args):
    output = subprocess.check_output(["oci", *args, "--output", "json"], timeout=120)
    return json.loads(output)["data"]


def inspect(tenancy):
    homes = [row["region-name"] for row in query("iam", "region-subscription", "list",
             "--tenancy-id", tenancy, "--all") if row["is-home-region"]]
    if len(homes) != 1:
        raise ValueError("Could not determine one home region")
    region = homes[0]
    scope = ("--region", region, "--compartment-id", tenancy)
    rows = []
    for ad in query("iam", "availability-domain", "list", *scope, "--all"):
        name = ad["name"]
        limits = {}
        for suffix in ("core", "memory"):
            result = query("limits", "resource-availability", "get", *scope,
                           "--service-name", "compute", "--availability-domain", name,
                           "--limit-name", f"standard-a1-{suffix}-count")
            limits[suffix] = {k: result.get(k) for k in ("used", "available")}
        shape = [{"instanceShape": SHAPE, "instanceShapeConfig": CONFIG}]
        report = query("compute", "compute-capacity-report", "create", *scope,
                       "--availability-domain", name, "--shape-availabilities", json.dumps(shape))
        rows.append({"availability_domain": name, "a1_limits": limits,
                     "reported_capacity": [r["availability-status"] for r in report["shape-availabilities"]
                                           if r["instance-shape"] == SHAPE]})
    if not rows:
        raise ValueError("No availability-domain evidence")
    return {"measured_utc": datetime.now(timezone.utc).isoformat(), "home_region": region,
            "requested_shape": SHAPE, "requested_shape_config": CONFIG, "domains": rows,
            "billing_review": "Required: remaining monthly free hours, storage and all planned services.",
            "provisioned": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenancy", default=os.environ.get("OCI_TENANCY"), help="root tenancy OCID")
    args = parser.parse_args()
    if not (args.tenancy or "").startswith("ocid1.tenancy."):
        parser.error("supply a root tenancy OCID in Cloud Shell")
    try:
        print(json.dumps(inspect(args.tenancy), indent=2))
    except (OSError, subprocess.SubprocessError, KeyError, ValueError) as error:
        sys.exit("Capacity evidence unavailable: " + type(error).__name__)
