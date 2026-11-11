"""Archive and retire ONLY SHA-pinned, already-merged November release branches.

Never rewrite main. Fail closed on moved refs, unmerged PRs, unexpected/open
branches, incomplete pagination, or changed main. Dry-run unless --apply.
The GitHub REST DELETE endpoint has no compare-and-swap; recheck immediately
before deletion and allow this maintenance to run only without active PRs.
"""
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request

REPO = "Frotan2/TOFEL-House-ERP"
SELF_BRANCH = "maintenance/retire-merged-release-branches-20261111"
ARCHIVE = "archive/toefl-house-merged-20261111"
# PR number, exact merged PR head ref, exact commit; never infer from prefix.
CANDIDATES = (
    (155, "fix/windows-offline-docker-inspect-defaults", "0553dc80bfb5f4cf3afe6c898ff65dbf460d9650"),
    (156, "fix/reception-receipt-action-scope", "ceac8b18b0385a2d91558dfb3295c85a4aecf585"),
    (157, "fix/admission-browser-version", "1398591c55b8193bc320d9b983bf1429aa133baf"),
    (158, "fix/installment-browser-integer", "ff5a34329fef18c996bbe480e0ccc72fafd94886"),
    (159, "fix/company-scoped-tuition-plan", "d68f0ba66b98e61f96c0fb4709ac0d7258d8b8c7"),
    (160, "fix/staff-course-assessment", "4e4dc08f2d62d80563a9ddd0ac333f6760d40ee5"),
    (161, "fix/reception-linked-applicant-branch", "7ca9b64eb8cef378d972d6fca509526374742059"),
    (162, "maintenance/release-evidence-20261111", "7bafe6f1564da83164b77174bfad84cd37a9f22a"),
)


def api(method, path, payload=None, *, absent_ok=False):
    encoded = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + path, method=method, data=encoded,
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "toefl-house-safe-merged-branch-cleanup"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        if absent_ok and exc.code == 404:
            return None
        raise RuntimeError(f"GitHub {method} request failed: {exc.code} {path}") from exc


def ref_path(branch, kind="heads"):
    if not branch or branch == "main" or branch.startswith("refs/") or ".." in branch:
        raise ValueError("Unsafe ref name")
    return "/git/ref/" + kind + "/" + urllib.parse.quote(branch, safe="/")


def list_page(path):
    result = api("GET", path + ("&" if "?" in path else "?") + "per_page=100")
    if not isinstance(result, list) or len(result) >= 100:
        raise RuntimeError("Cannot establish complete unpaginated inventory")
    return result


def is_eligible(pr, expected, branch_ref, open_pulls):
    number, branch, sha = expected
    if (pr.get("number") != number or pr.get("state") != "closed" or
        not pr.get("merged_at") or (pr.get("base") or {}).get("ref") != "main"):
        return False
    head = pr.get("head") or {}
    if (head.get("repo") or {}).get("full_name") != REPO or head.get("ref") != branch or head.get("sha") != sha:
        return False
    if not branch_ref or branch_ref.get("ref") != "refs/heads/" + branch or (branch_ref.get("object") or {}).get("sha") != sha:
        return False
    return not any((p.get("head") or {}).get("ref") == branch for p in open_pulls)


def candidate_plan(main_sha):
    open_pulls = list_page("/pulls?state=open")
    if open_pulls:
        raise RuntimeError("Open pull requests exist: refuse branch cleanup")
    recent = list_page("/pulls?state=closed")
    own = [p for p in recent if (p.get("head") or {}).get("ref") == SELF_BRANCH and
           (p.get("head") or {}).get("repo", {}).get("full_name") == REPO and
           (p.get("base") or {}).get("ref") == "main" and p.get("merged_at")]
    if len(own) != 1:
        raise RuntimeError("Exact merged cleanup PR cannot be identified")
    cleanup = own[0]
    candidates = list(CANDIDATES) + [(cleanup["number"], SELF_BRANCH, cleanup["head"]["sha"])]
    if len({b for _, b, _ in candidates}) != len(candidates):
        raise RuntimeError("Duplicate branch in allowlist")
    inventory = {x["name"]: x["commit"]["sha"] for x in list_page("/branches")}
    extra = set(inventory) - ({"main"} | {b for _, b, _ in candidates})
    if extra or inventory.get("main") != main_sha:
        raise RuntimeError("Unexpected branch or changed main: " + repr(sorted(extra)))
    plan = []
    for expected in candidates:
        number, branch, sha = expected
        pr = api("GET", "/pulls/" + str(number))
        current = api("GET", ref_path(branch), absent_ok=True)
        if current is None:
            if branch in inventory:
                raise RuntimeError("Ref disappeared mid-inventory: " + branch)
            continue  # idempotent rerun after prior successful deletion
        if not is_eligible(pr, expected, current, open_pulls):
            raise RuntimeError("Not a safely merged unchanged PR: " + branch)
        if inventory.get(branch) != sha:
            raise RuntimeError("Branch moved since inventory: " + branch)
        # GitHub merge commits preserve PR history. Do not delete a ref whose
        # head is not reachable from the exact current main.
        compare = api("GET", "/compare/" + main_sha + "..." + sha)
        if compare.get("ahead_by") != 0:
            raise RuntimeError("Branch has unmerged commits: " + branch)
        plan.append(expected)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    expected_main = os.environ.get("GITHUB_SHA", "")
    if (os.environ.get("GITHUB_REPOSITORY") != REPO or
        os.environ.get("GITHUB_REF") != "refs/heads/main" or
        not os.environ.get("GITHUB_TOKEN") or
        len(expected_main) != 40):
        raise RuntimeError("Requires exact main GitHub Actions context")
    if api("GET", "/git/ref/heads/main")["object"]["sha"] != expected_main:
        raise RuntimeError("Main changed before preflight")
    plan = candidate_plan(expected_main)
    print("Exact merged heads verified:", len(plan))
    for number, branch, sha in plan:
        print("ELIGIBLE", number, branch, sha)
    if not args.apply:
        print("DRY RUN: no tags or branches changed")
        return

    # Archive EVERY eligible source before deleting ANY branch.
    for number, branch, sha in plan:
        tag = f"{ARCHIVE}/pr-{number}-{sha[:12]}"
        url = ref_path(tag, "tags")
        found = api("GET", url, absent_ok=True)
        if found is None:
            api("POST", "/git/refs", {"ref": "refs/tags/" + tag, "sha": sha})
        elif (found.get("object") or {}).get("sha") != sha:
            raise RuntimeError("Archive tag collision for " + branch)
        verified = api("GET", url)
        if verified["object"]["sha"] != sha:
            raise RuntimeError("Archive verification failed for " + branch)

    for number, branch, sha in plan:
        if api("GET", "/git/ref/heads/main")["object"]["sha"] != expected_main:
            raise RuntimeError("Main moved during cleanup")
        pr = api("GET", "/pulls/" + str(number))
        current = api("GET", ref_path(branch), absent_ok=True)
        if not is_eligible(pr, (number, branch, sha), current, list_page("/pulls?state=open")):
            raise RuntimeError("Recheck failed before deletion: " + branch)
        api("DELETE", "/git/refs/heads/" + urllib.parse.quote(branch, safe="/"))
        if api("GET", ref_path(branch), absent_ok=True) is not None:
            raise RuntimeError("Branch not deleted: " + branch)
        print("ARCHIVED AND DELETED", branch)
    remaining = {x["name"] for x in list_page("/branches")}
    if remaining != {"main"} or api("GET", "/git/ref/heads/main")["object"]["sha"] != expected_main:
        raise RuntimeError("Unexpected post-cleanup branch or main ref")
    print("SUCCESS: only main branch; source heads preserved as immutable archive refs")


if __name__ == "__main__":
    main()
