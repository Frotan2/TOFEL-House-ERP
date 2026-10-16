# ECharts presence check — 2026-10-15 (GHSA-fgmj-fm8m-jvvx / CVE-2026-45249)

Purpose: close the erratum E2 condition. The 2026-10-03 disposition was BLOCKED
because the earlier NOT_REACHABLE reasoning could not be reproduced. This record
establishes, with reproducible evidence, whether `echarts` is present in any
shipped dependency tree.

## Reproduction (run from any empty directory, network to github.com/codeload and registry.npmjs.org)

```
for spec in "erpnext 4048fb70e14d1843956fcdabb7c3cca75a1cbcdd" \
            "education 93bc7075753369457919720690f80c6d2207b5f2" \
            "payments cca07d9f9392e2ea0e521c5975151db9e4b6c321" \
            "hrms a4768b441cff346def505e27f2a2229ee1e05b9b" \
            "frappe 988e54f3c4c291e2077a83809663f123731abe76"; do
  set -- $spec
  curl -sSL -o $1.tgz https://codeload.github.com/frappe/$1/tar.gz/$2
  mkdir -p $1 && tar -xzf $1.tgz -C $1 --strip-components=1
  echo "$1 lock/manifest hits: $(grep -ril echarts $1 --include=yarn.lock --include=package-lock.json --include=package.json | wc -l)"
  echo "$1 source hits:        $(grep -ril echarts $1 | wc -l)"
done
# frappe-ui range -> version -> dependency check
curl -s https://registry.npmjs.org/frappe-ui/0.1.278 | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['dependencies'].get('echarts'))"   # -> ^5.6.0
```

Also: `git grep -il echarts` on this repository returns documentation files only.

## Results (see presence-table.md and results.json)

- Zero lockfile, manifest and source hits for `echarts` in erpnext, education, payments, hrms (frontend and roster), and frappe at the pinned SHAs.
- Zero hits in the repository's tracked code and lock copies (`tools/foundation/*-locks`).
- frappe-ui is resolved to 0.1.31 (education, frozen lock) and 0.1.105 (hrms frontend and roster, frozen lock). Neither depends on echarts.
- frappe-ui 0.1.31 and 0.1.105 declare no echarts dependency. frappe-ui 0.1.278 declares `echarts ^5.6.0`, the route described in erratum E2. It is in no pinned lock.

## Conditions and residual exposure

1. The route exists only if a non-frozen resolution moves education's `frappe-ui ^0.1.17` range to 0.1.278 or later. Installs are frozen in `product/app.Dockerfile` (`~/.yarnrc`, `--install.frozen-lockfile true`) and in `tools/foundation/runtime_install.py` (`.yarnrc` written for the lab). Tripwire: `tests/security/test_echarts_presence_2026_10_15.py` asserts the frozen controls and the recorded results.
2. Any change to a pinned SHA, to a frappe-ui range, or to a frozen-install control requires re-running the reproduction and re-triage.
3. Upstream action (not blocking the product): education's frontend manifest keeps the caret range `^0.1.17`. Upstream may pin it exactly.
