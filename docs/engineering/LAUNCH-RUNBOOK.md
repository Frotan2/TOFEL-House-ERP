# Launch runbook — production activation

Owner-run procedure that switches a site from the fail-closed default (every
TOEFL House command REFUSED) to production operation, and back. Native
ERPNext/Education/HRMS work without it. Do not activate while SEC-DEPS-01 is
open on an internet-reachable host (see [../PRODUCT.md](../PRODUCT.md) §6).

**Desktop product (Owner):** do not type any of the commands below. Run
`Backup TOEFL House ERP.cmd`, then `Activate TOEFL House ERP.cmd` (type
`ACTIVATE`). It runs `product/activate.py` inside the container, which performs
steps 0–6 exactly as written here: it refuses without a database backup from
the last 24 hours, saves the old site_config to `private/`, and verifies with
the app's own resolver. If any gate fails it restores the saved settings. The
same window optionally sets the step-7 fee Item, which must already exist.
`Deactivate TOEFL House ERP.cmd` is step 8. The procedure below remains the
reference and the path for an authorized server.

Conventions: commands below are written for the bench directory. On the
desktop product, run them inside the web container from the repository
folder: `docker compose -f product/docker-compose.yml exec web <command>`
(the bench directory is the container's working directory and `bench` is
`/build/tools/bin/bench`). `SITE` is the site name (`toeflhouse.localhost` on
the desktop product). `<ts>` is a timestamp like `20260919-1200`.

---

## 0. Preconditions (do not proceed unless all hold)

1. The site runs the current release (latest image built from this
   repository,
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

## 9. Multi-user access (central server + Tailscale)

The current deployment (owner decision D15) is one central computer
running the product, with authorized staff computers accessing it through the
owner's Tailscale tailnet. The product does not change for this: it keeps
listening on `127.0.0.1` only, and the tailnet reach comes from **Tailscale
Serve**, which is external to the product and stays under the owner's
Tailscale account (identity, ACLs, device list).

Setup (once per central PC; every staff PC only needs Tailscale joined to
the tailnet):

1. Start the ERP on the central PC (`Start TOEFL House ERP.cmd`).
2. Operator step on the central PC (a terminal is fine; it is not part of
   the double-click flow):

   ```
   tailscale serve --bg 8000
   ```

   This publishes the ERP to the tailnet as HTTPS on the central PC's
   Tailscale hostname. It opens no public port: without Funnel (never
   enable it for this product), only tailnet members can reach it.
3. On each staff PC, open
   `https://<central-PC-name>.<your-tailnet-name>.ts.net/` in the browser.
   The Tailscale certificate is trusted on all tailnet machines (MagicDNS is
   on by default).
4. Each staff member logs in with their own native User (User and Role are
   the identity authority; branch-scoped staff additionally carry a native
   User Permission for their Branch — `docs/ROLE-DESKS.md`, "Branch
   scope").

Properties and limits:

- Access control is Tailscale identity plus the ERP's own users and roles;
  no public address, no firewall rule, no open host port is involved.
- The product resolves its single site independently of the hostname in the
  URL (`product/wsgi.py` pins the site), so the tailnet hostname needs no
  site configuration.
- Live realtime desk refresh over the tailnet is qualified for the current
  deployment. SocketIO is routed through Tailscale Serve on the same HTTPS
  origin, and the multi-user qualification proves a second client can use
  realtime plus restart persistence. Do not publish the raw SocketIO port or
  enable Funnel; any topology change still requires a new qualification.
- Removing the tailnet exposure at any time: run
  `tailscale serve --delete` on the central PC. The ERP remains
  loopback-only; nothing else is affected.

## 10. Restore from backup (operator)

The `Backup TOEFL House ERP.cmd` script writes a full backup triplet
(`*-database.sql.gz`, `*-files.tar`, `*-private-files.tar`) into
`data\sites\toeflhouse.localhost\private\backups`. Restoring one of them is a
guided operator step, not a double-click (a restore overwrites data):

1. Keep the ERP running (start it first if it is stopped). The restore runs
   inside the web container, so the stack must be up — `Stop TOEFL House
   ERP.cmd` runs `docker compose down`, which removes the container the
   restore executes in. Choose a moment when nobody is mid-command; the
   restore takes a few seconds.
2. Copy the chosen triplet (from the external drive) into
   `data\sites\toeflhouse.localhost\private\backups` — its original
   location; no other copy is needed.
3. Operator step in a terminal inside the product folder (the paths are
   relative to the bench directory inside the web container, which is where
   bench resolves them from):

   ```
   docker compose exec web /build/tools/bin/bench --site toeflhouse.localhost restore "sites/toeflhouse.localhost/private/backups/<triple name>-database.sql.gz" --with-public-files "sites/toeflhouse.localhost/private/backups/<triple name>-files.tar" --with-private-files "sites/toeflhouse.localhost/private/backups/<triple name>-private-files.tar" --db-root-password <password from data\secrets\db.env> --admin-password <Administrator password from data\sites\toeflhouse.localhost\private\first-run-credentials.txt>
   ```

4. `docker compose restart web` (a terminal step, same folder), then log in;
   confirm the expected records are present.
5. Record the rehearsal: date, triple name, elapsed time, outcome.

Activation is site config, not database data (steps 3 and 8 above): a
restore returns the data to the backup point while the site keeps whatever
activation state `site_config.json` currently carries.

## 11. Record the rehearsal

The Owner runs this runbook on the local server and records each run. A successful local Bench backup/restore rehearsal is necessary evidence but does not by itself close D14: the Owner-controlled off-site encrypted copy and its restore must also be evidenced:

| Date | Site | Step-4 site_mode | Step-5 mirror | Step-6 mixed | Elapsed | Outcome |
| ---- | ---- | ---------------- | ------------- | ------------ | ------- | ------- |
|      |      |                  |               |              |         |         |

Activation is a mechanism, not a GO decision. SEC-DEPS-01 (known upstream
advisories in the pinned stack) gates **internet exposure** of the product;
it is not a stop for the selected loopback / local-Tailscale deployment
(owner decisions D13/D15). The current evidence state of the acceptance
items (backup, branch isolation, rollback, monitoring, capacity) is recorded
in `docs/engineering/ACCEPTANCE.md`.
