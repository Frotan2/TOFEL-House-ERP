"""Final branch retirement, SHA-pinned and fail-closed. Main is never deleted.

Only run from the explicit main-branch maintenance workflow after PR #69
has merged. Superseded agent heads have named, verified replacement PRs.
Dry-run unless --apply is passed with CI authorization.
"""
import argparse
import os
import sys
import urllib.error
import urllib.parse

from retire_merged_branches import api, delete_ref_path, eligible, open_pulls

REPOSITORY = "Frotan2/TOFEL-House-ERP"
SELF_BRANCH = "maintenance/retire-receipt-currency-fix-20261025"
# (original PR number or None, exact branch, audited head SHA, replacement PR or None)
# The replacement mapping is for intentionally closed, unmerged/obsolete
# implementations; it is never permission to retire an open PR or a moved head.
CANDIDATES = (
    (57, "arena/aef07999-tofel-house-erp", "f325181395b38473e69814a0f80dd4f4c6ea1dfd", None),
    (61, "arena/bef6fb1b-tofel-house-erp", "09607131f42bb5e21d0a4f6a06247570e4a65258", 62),
    (58, "arena/e281e864-tofel-house-erp", "b5c5b2ca6bc189c3976e73e37f2eb0894daaf71d", 65),
    (52, "arena/f3ce64a9-tofel-house-erp", "beaf67a10f3eff3980cf24a3f59d1679de2ea955", None),
    (49, "arena/f83343be-tofel-house-erp", "c93f7dbd162a63eeccc37c055655269f94b41eec", 64),
    (46, "arena/fa9a38ba-tofel-house-erp", "e8145954cdc081e84cc8aa2356e152c5ceda415d", 62),
    (51, "arena/197fb66a-tofel-house-erp", "4d0fcceb1a06c78c96ba378d1edc5ef3dd70bcc4", 69),
    (50, "arena/2537b25b-tofel-house-erp", "58d3ebfa47d537e4d82e33214aa4b14be175350e", None),
    (48, "arena/82235d06-tofel-house-erp", "b8d83fa1fdab9a6d9e92f8a33f9bec652a4f5f6c", 69),
    (67, "ci/release-gate-ref-isolation-20261025", "a326162e84b1e80317757712fa4dca742f5c7020", None),
    (64, "integration/academic-main-20261024", "70d509e98c47e431f0042924688dd953277d52b4", None),
    (62, "integration/consolidated-windows-updater-20261024", "3eb51bdb21e4a781ec224d15afe7151183fb93ff", None),
    (63, "integration/fix-live-role-desk-browser-20261024", "0d86f3e112b979cd40d0b600ec5c8cccf21aa454", None),
    (None, "integration/merge-verified-ux-after-finance-20261024", "481d265f2a52e106bb0fdf6985592be1ca9b74f9", 65),
    (60, "integration/repair-native-four-eyes-fixtures-20261024", "d9cf55415dfc0a5ae7d8b0709382f74bc05e6ef2", None),
    (66, "integration/verified-portals-alerts-20261025", "49bef05fce880871aa3b5752d8a709c2ed1dea1d", 69),
    (65, "integration/verified-role-desks-20261024", "50c1d70dd5f1772a614f8ee6c26dd0a94c3c9a9d", None),
    (59, "security/harden-owner-branch-attendance-approvals-20261024", "06afeef0d7da65eb2cd25905e51605496c37c349", None),
    (69, "integration/final-operations-20261025", "6c6eaa59ab43d90832de3da39cf279325425168c", None),
    (72, "fix/deferred-policy-and-owner-metrics-20261025", "1ddd436a75d30b8ed96b044b73069300e123c0f2", None),
    (74, "fix/owner-desk-plain-language-native-20261025", "2bfbca38e573bfb8d0fdfb2820fe14c7e9555231", None),
    (77, "fix/owner-analytics-complete-coverage-20261025", "6877aaec8dbacfe441156edc92c13a5e7770ce17", None),
    (80, "fix/manager-funnel-completeness-d7-20261025", "b4819ac1e751c6178188525cf80d878a1de6dbb1", None),
    (81, "fix/receipt-currency-owner-report-20261025", "74a63ae5600eadb8a7de33990a22fb9c4f20ccf5", None),
)


def pr_is_merged(pr, head=None):
    return bool(
        pr and pr.get("state") == "closed" and pr.get("merged_at")
        and (pr.get("base") or {}).get("ref") == "main"
        and (head is None or (pr.get("head") or {}).get("sha") == head)
    )


def ref_path(branch):
    if not branch or branch == "main" or branch.startswith("refs/"):
        raise ValueError("Unsafe branch name")
    return "/git/ref/heads/" + urllib.parse.quote(branch, safe="/")


def is_open(opened, branch):
    return any(
        (pr.get("head") or {}).get("ref") == branch
        and ((pr.get("head") or {}).get("repo") or {}).get("full_name") == REPOSITORY
        for pr in opened
    )


def verify_replacement(num):
    pr = api("/pulls/" + str(num), TOKEN)
    if not pr_is_merged(pr):
        raise RuntimeError(f"Replacement PR #{num} has not merged into main")
    return pr


def all_branches():
    branches = []
    for page in range(1, 11):
        batch = api(f"/branches?per_page=100&page={page}", TOKEN)
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected branch API payload")
        branches.extend(branch["name"] for branch in batch)
        if len(batch) < 100:
            return branches
    raise RuntimeError("More than 1,000 branches: refusing")


def self_merged_pr():
    for page in range(1, 11):
        batch = api(f"/pulls?state=closed&per_page=100&page={page}", TOKEN)
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected closed PR payload")
        for pr in batch:
            if ((pr.get("head") or {}).get("ref") == SELF_BRANCH
                    and pr_is_merged(pr)
                    and ((pr.get("head") or {}).get("repo") or {}).get("full_name") == REPOSITORY):
                return pr
        if len(batch) < 100:
            break
    raise RuntimeError("Final cleanup PR has not merged")


def permitted(original, branch, sha, replacement, opened):
    if is_open(opened, branch):
        return False, "head is still used by an open PR"
    path = ref_path(branch)
    try:
        ref = api(path, TOKEN)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None, "already absent"
        raise
    if ref.get("ref") != "refs/heads/" + branch or (ref.get("object") or {}).get("sha") != sha:
        return False, "ref changed from audited SHA"
    if original is not None:
        pr = api("/pulls/" + str(original), TOKEN)
        h = pr.get("head") or {}
        if (h.get("ref") != branch or h.get("sha") != sha
                or (h.get("repo") or {}).get("full_name") != REPOSITORY):
            return False, "PR head no longer matches audited branch"
        if replacement is None:
            ok, reason = eligible(pr, ref, opened, branch, sha)
            return ok, reason
        if pr.get("state") != "closed":
            return False, "superseded source PR is not closed"
    if replacement is not None:
        verify_replacement(replacement)
        return True, f"exact frozen head, replaced by merged PR #{replacement}"
    return False, "unverifiable provenance"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    global TOKEN
    TOKEN = os.environ.get("GITHUB_TOKEN", "")
    if not TOKEN or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        print("FAIL CLOSED: token or repository is missing", file=sys.stderr)
        return 2
    if args.apply and (
        os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("CONFIRM_FINAL_BRANCH_RETIREMENT") != "exact-24-heads-after-pr81"
    ):
        print("FAIL CLOSED: main workflow authorization required", file=sys.stderr)
        return 2
    try:
        # No cleanup until the two outstanding major feature lines have been
        # reconciled into a merged, reviewed integration PR.
        verify_replacement(69)
        verify_replacement(81)
        if not api("/contents/apps/toefl_house/toefl_house/teaching/transfers.py?ref=main", TOKEN):
            raise RuntimeError("Class transfer implementation missing from main")
        if not api("/contents/apps/toefl_house/toefl_house/operations/guardian_portal.py?ref=main", TOKEN):
            raise RuntimeError("Guardian portal implementation missing from main")
        opened = open_pulls(TOKEN)
        self_pr = self_merged_pr()
        candidates = list(CANDIDATES) + [
            (self_pr["number"], SELF_BRANCH, self_pr["head"]["sha"], None)
        ]
        actual = set(all_branches())
        expected = {"main"} | {branch for _, branch, _, _ in candidates}
        unexpected = sorted(actual - expected)
        if unexpected:
            raise RuntimeError("Unexpected live branch(es): " + ", ".join(unexpected))
        blocked = []
        selected = []
        for original, branch, sha, replacement in candidates:
            result, reason = permitted(original, branch, sha, replacement, opened)
            print(("ELIGIBLE" if result else "ABSENT" if result is None else "KEEP"), branch, reason)
            if result is True:
                selected.append((original, branch, sha, replacement))
            if result is False:
                blocked.append(branch)
        if blocked:
            raise RuntimeError("No deletion because heads need review: " + ", ".join(blocked))
        if not args.apply:
            print("DRY RUN: eligible", len(selected), "of", len(candidates))
            return 0
        for original, branch, sha, replacement in selected:
            # Re-read PR, open PRs and live SHA before every destructive call.
            result, reason = permitted(original, branch, sha, replacement, open_pulls(TOKEN))
            if result is not True:
                raise RuntimeError(f"Stop, branch changed before deletion: {branch}: {reason}")
            api(delete_ref_path(ref_path(branch)), TOKEN, "DELETE")
            print("DELETED", branch, sha)
        remaining = set(all_branches())
        if remaining != {"main"}:
            raise RuntimeError("Remaining branches: " + repr(sorted(remaining)))
        print("VERIFIED: main is the only remaining branch")
        return 0
    except (RuntimeError, ValueError, KeyError, TypeError, urllib.error.URLError) as exc:
        print("FAIL CLOSED:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
