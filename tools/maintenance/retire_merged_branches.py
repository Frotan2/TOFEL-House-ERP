"""One-shot, exact-SHA cleanup of seven verified merged PR branches.

DRY-RUN by default. Never deletes main, any changed branch, unmerged PR,
or the head of an open pull request. Requires explicit main CI context for apply.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "Frotan2/TOFEL-House-ERP"
CANDIDATES = (
    (37, "fix/verify-customer-image-layers", "dee4ebb4a012c9e25493570d4cd2146b379d68e0"),
    (39, "security/patch-filelock-setuptools", "2184ac7088d53bb7e9a8b1f23d48c1d0aa9aa124"),
    (42, "security/setuptools-windows-boundary-evidence", "3d3341181c7f3798100da44dabf11b6a6b69ab28"),
    (43, "arena/87e5b438-tofel-house-erp", "dbead2aee6601d5fab126a1f8d1d6a8cad796b47"),
    (44, "release/atomic-customer-archives", "c80f9250d5214c95617f670571ed5eeb9bb943e7"),
    (45, "finance/strict-book-ledger-reconciliation", "17dda4de3ccdb1ec00ed39729b3c0e3cc1d4bf0d"),
    (47, "release/trigger-image-for-native-commerce", "2d9d28dbc7517320fd2c69328d21dc964dff155b"),
)


def eligible(pr, ref, opened, branch, sha):
    if branch == "main" or branch.startswith("refs/"):
        return False, "protected or malformed branch"
    if pr.get("state") != "closed" or not pr.get("merged_at"):
        return False, "pull request is not merged"
    head = pr.get("head") or {}
    if (head.get("repo") or {}).get("full_name") != REPOSITORY or head.get("ref") != branch or head.get("sha") != sha:
        return False, "unexpected PR head"
    if ref.get("ref") != "refs/heads/" + branch or (ref.get("object") or {}).get("sha") != sha:
        return False, "branch moved after audit"
    for other in opened:
        h = other.get("head") or {}
        if h.get("ref") == branch and (h.get("repo") or {}).get("full_name") == REPOSITORY:
            return False, "branch is still used by an open PR"
    return True, "unchanged merged PR head, with no open PR"


def api(path, token, method="GET"):
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPOSITORY + path,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "TOEFL-House-ERP-merged-branch-maintenance",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = response.read()
    return json.loads(payload) if payload else None


def delete_ref_path(read_path):
    """GitHub reads /git/ref/{ref} but deletes /git/refs/{ref}."""
    if not read_path.startswith("/git/ref/heads/"):
        raise ValueError("Ref deletion path must be within heads")
    return read_path.replace("/git/ref/", "/git/refs/", 1)


def open_pulls(token):
    out = []
    for page in range(1, 101):
        batch = api("/pulls?state=open&per_page=100&page=" + str(page), token)
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected PR-list response; stop")
        out.extend(batch)
        if len(batch) < 100:
            return out
    raise RuntimeError("Too many PR pages; stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        print("Missing token or wrong repository; refusing", file=sys.stderr)
        return 2
    if args.apply and (
        os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("CONFIRM_MERGED_BRANCH_CLEANUP") != "seven-exact-merged-pr-branches"
    ):
        print("Deletion requires explicit main-branch workflow approval", file=sys.stderr)
        return 2
    try:
        opened = open_pulls(token)
        selected = []
        for number, branch, sha in CANDIDATES:
            path = "/git/ref/heads/" + urllib.parse.quote(branch, safe="/")
            pr = api("/pulls/" + str(number), token)
            try:
                ref = api(path, token)
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    print("ALREADY ABSENT:", branch)
                    continue
                raise
            ok, reason = eligible(pr, ref, opened, branch, sha)
            print(("ELIGIBLE: " if ok else "KEEP: ") + branch + " — " + reason)
            if ok:
                selected.append((number, branch, sha, path))
        if not args.apply:
            print("DRY RUN: eligible", len(selected), "of", len(CANDIDATES))
            return 0
        for number, branch, sha, path in selected:
            # Verify again to avoid deleting a branch reused since preflight.
            ok, reason = eligible(
                api("/pulls/" + str(number), token),
                api(path, token),
                open_pulls(token),
                branch,
                sha,
            )
            if not ok:
                print("KEEP after recheck:", branch, reason)
                continue
            api(delete_ref_path(path), token, "DELETE")
            print("DELETED:", branch, "PR", number, "SHA", sha)
        return 0
    except (urllib.error.URLError, ValueError, RuntimeError, TypeError) as error:
        print("FAIL CLOSED:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
