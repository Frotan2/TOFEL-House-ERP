# Launch runbook — local server + Tailscale (D15 scope)

Owner-run procedure for the authorized launch target only: the local server
reached over Tailscale. No internet edge is authorized (D15); production
stays **REJECT** until the gates close, and SEC-DEPS-01 stays a hard stop.

Conventions: run every command from the bench directory (`frappe-bench/`)
as the bench owner user. Replace `SITE` with the production site name
(the directory name under `sites/`, e.g. `erp.toeflhouse.tailnet`).
`<ts>` is a timestamp like `20260919-1200`.

---

## 0. Preconditions (do not proceed unless all hold)

1. The bench runs this release (branch `arena/01a0ba0d-tofel-house-erp`,
   D16 activation code deployed and migrated).
2. MariaDB is the backend (the app refuses any other backend).
3. You hold a current encrypted backup and have rehearsed a restore.
4. `SITE` is **not** `placement-test.localhost` or
   `placement-second.localhost` — the qualification hostnames can never be
   the production site; activation on them refuses.

## 1. Back up the current site config

```bash
cp sites/SITE/site_config.json /var/backups/toefl-house/site_config.json.<ts>.bak
sha256sum sites/SITE/site_config.json
```

## 2. Confirm the site is currently REFUSED (pre-activation baseline)

```bash
bench --site SITE show-config
bench --site SITE execute toefl_house.security.site_mode
```

Expected: `show-config` shows **neither** `toefl_house_production_active`
**nor** `toefl_house_production_site`, and the `execute` prints `REFUSED`.
If it prints anything else, stop — the site is already configured; resolve
before continuing.

## 3. Write the activation triple

Set the two keys with exact JSON types (`1` is a number, the site name is
a string equal to the running site). Edit `sites/SITE/site_config.json`
directly so the types are unambiguous:

```bash
python3 - SITE <<'EOF'
import json, sys
path = f"sites/{sys.argv[1]}/site_config.json"
with open(path) as handle:
    config = json.load(handle)
for stale in ("toefl_house_synthetic_only", "allow_tests"):
    if stale in config:
        raise SystemExit(f"refusing: {stale} is present; remove it first (step 6)")
config["toefl_house_production_active"] = 1
config["toefl_house_production_site"] = sys.argv[1]
with open(path, "w") as handle:
    json.dump(config, handle, indent=2)
    handle.write("\n")
print("activation triple written")
EOF
```

(`bench --site SITE set-config KEY VALUE` is the documented alternative
for site-config edits; if you use it, the step-4 verification below is
mandatory because a mistyped value fails closed to REFUSED.)

## 4. Verify activation (hard gates — all must pass)

```bash
bench --site SITE show-config
bench --site SITE execute toefl_house.security.site_mode
bench --site SITE execute toefl_house.security.record_synthetic_flag
```

Expected:

- `show-config` lists `"toefl_house_production_active": 1` and
  `"toefl_house_production_site": "SITE"`, and lists **neither**
  `toefl_house_synthetic_only` **nor** `allow_tests`.
- `site_mode` prints `PRODUCTION`.
- `record_synthetic_flag` prints `0` (production stamps, not fixture stamps).

Site config is read on each request, so no process restart is required; if
a worker still reports the old mode, run `bench restart` and re-verify.

## 5. Verify the fixture mirror (negative checks)

On the activated site, test fixtures must be refused. In a console
(`bench --site SITE console`):

```python
from toefl_house.security import site_mode
assert site_mode() == "PRODUCTION"
from toefl_house import policy
for bad in ("SYN-PLACE-1", "SYNTHETIC-X"):
    try:
        policy.validate_family(bad, 1, production=True)
    except ValueError:
        pass
    else:
        raise SystemExit(f"refusing: fixture code accepted: {bad}")
policy.validate_family("FALL-2026-A", 1, production=True)
print("fixture mirror OK")
```

On any non-activated site the same `execute` from step 4 must print
`REFUSED`, and `record_synthetic_flag` must raise instead of stamping.

## 6. Mixed-mode refusal check (do not skip on first activation)

Temporarily add one synthetic flag, confirm refusal, then remove it:

```bash
python3 - SITE <<'EOF'
import json, sys
path = f"sites/{sys.argv[1]}/site_config.json"
with open(path) as handle:
    config = json.load(handle)
config["toefl_house_synthetic_only"] = 1
config["allow_tests"] = 1
with open(path, "w") as handle:
    json.dump(config, handle, indent=2)
    handle.write("\n")
print("mixed mode staged")
EOF
bench --site SITE execute toefl_house.security.site_mode
```

Expected: `REFUSED`. Then remove the staged flags and re-verify `PRODUCTION`:

```bash
python3 - SITE <<'EOF'
import json, sys
path = f"sites/{sys.argv[1]}/site_config.json"
with open(path) as handle:
    config = json.load(handle)
for staged in ("toefl_house_synthetic_only", "allow_tests"):
    config.pop(staged, None)
with open(path, "w") as handle:
    json.dump(config, handle, indent=2)
    handle.write("\n")
print("mixed mode cleared")
EOF
bench --site SITE execute toefl_house.security.site_mode
```

Expected: `PRODUCTION`.

## 7. Configure the production placement-fee item (before first billing)

On synthetic sites the placement fee bills through the `SYN-PLACEMENT-FEE`
fixture item. That marker is forbidden on production, so
`issue_placement_fee` fails closed until Finance configures a real native
Item code here:

```bash
python3 - SITE PLACEMENT-ITEM-CODE <<'EOF'
import json, sys
path = f"sites/{sys.argv[1]}/site_config.json"
item = sys.argv[2]
assert item and len(item) <= 140 and not item.startswith("SYN-") \
    and not item.startswith("SYNTHETIC"), "fixture markers are forbidden"
with open(path) as handle:
    config = json.load(handle)
config["toefl_house_placement_fee_item"] = item
with open(path, "w") as handle:
    json.dump(config, handle, indent=2)
    handle.write("\n")
print("placement fee item configured")
EOF
```

The Item must exist natively with a positive selling rate on the
`TOEFL House Standard` price list, or the command stays denied.

## 8. Rollback (deactivation)

Removing the activation keys returns the site to REFUSED immediately:

```bash
python3 - SITE <<'EOF'
import json, sys
path = f"sites/{sys.argv[1]}/site_config.json"
with open(path) as handle:
    config = json.load(handle)
for key in ("toefl_house_production_active", "toefl_house_production_site"):
    config.pop(key, None)
with open(path, "w") as handle:
    json.dump(config, handle, indent=2)
    handle.write("\n")
print("activation removed")
EOF
bench --site SITE execute toefl_house.security.site_mode
```

Expected: `REFUSED`. No data migration is involved in either direction:
activation only changes which site mode the guards resolve.

## 9. Record the rehearsal

The Owner runs this runbook on the local server and records each run:

| Date | Site | Step-4 site_mode | Step-5 mirror | Step-6 mixed | Elapsed | Outcome |
| ---- | ---- | ---------------- | ------------- | ------------ | ------- | ------- |
|      |      |                  |               |              |         |         |

Activation is a mechanism, not a GO decision: it does not close SEC-DEPS-01,
the backup-restore rehearsal, TLS/session evidence, or any durability or
observability gate. Production stays **REJECT** until those close.
