#!/usr/bin/env bash
# Launch day: make github.com/rizdem/spoolhouse public, then lock it down. Safe to run again (it updates
# rather than duplicates). Needs the GitHub CLI logged in as the repo's owner (gh auth status).
#
#   tools/github_launch.sh            asks before making the repo public, then applies everything below
#   tools/github_launch.sh --check    only shows what's set now
#
# What it sets (see docs/LAUNCH.md):
#   main:      no force-push, no deleting; changes by pull request with the Mac and Windows tests passing
#              (you, as admin, can still push directly)
#   v* tags:   only you can create, move or delete them (a tag builds and publishes a release)
#   Actions:   read-only by default; pull requests from people new to the repo wait for your approval
#   Security:  secret scanning + push protection, Dependabot alerts + fixes, private vulnerability reports
#   Tidy:      Projects and Wiki off, Issues on, merged branches deleted
set -euo pipefail
REPO="rizdem/spoolhouse"
api() { gh api -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" "$@"; }

visibility=$(gh repo view "$REPO" --json visibility --jq .visibility)
echo "Repository: $REPO ($visibility)"

if [ "${1:-}" = "--check" ]; then
    echo "--- rulesets"; api "repos/$REPO/rulesets" --jq '.[] | "  \(.name): \(.enforcement)"' || true
    echo "--- Actions"; api "repos/$REPO/actions/permissions/workflow" --jq '"  default token: \(.default_workflow_permissions)"'
    echo "--- security"; api "repos/$REPO" --jq '.security_and_analysis // {} | to_entries[] | "  \(.key): \(.value.status)"'
    exit 0
fi

if [ "$visibility" != "PUBLIC" ]; then
    echo
    echo "It's private. Branch and tag rules only work on public repositories on GitHub's free plan,"
    echo "so the first step is making it public: everyone can then see and copy the code, its history"
    echo "and its releases (only you can change it). Draft releases stay hidden until you publish them."
    read -r -p "Type 'public' to make it public now (anything else stops here): " answer
    [ "$answer" = "public" ] || { echo "Stopped. Nothing changed."; exit 1; }
    gh repo edit "$REPO" --visibility public --accept-visibility-change-consequences
    echo "  now public"
fi

# a ruleset by name: update it if it's there, else create it
ruleset() {
    local name="$1" body="$2" id
    id=$(api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$name\") | .id" | head -n1)
    if [ -n "$id" ]; then
        echo "$body" | api -X PUT "repos/$REPO/rulesets/$id" --input - >/dev/null && echo "  updated: $name"
    else
        echo "$body" | api -X POST "repos/$REPO/rulesets" --input - >/dev/null && echo "  created: $name"
    fi
}

echo "--- Protecting main"
ruleset "Protect main" '{
  "name": "Protect main", "target": "branch", "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": true,
      "require_code_owner_review": false, "require_last_push_approval": false, "required_review_thread_resolution": false}},
    {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": false,
      "required_status_checks": [{"context": "test (macos-latest)"}, {"context": "test (windows-latest)"}]}}
  ]
}'

echo "--- Protecting release tags"
ruleset "Protect release tags" '{
  "name": "Protect release tags", "target": "tag", "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
  "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
  "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}, {"type": "non_fast_forward"}]
}'

echo "--- GitHub Actions"
api -X PUT "repos/$REPO/actions/permissions/workflow" -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false >/dev/null \
    && echo "  workflows get read-only access unless they ask for more"
api -X PUT "repos/$REPO/actions/permissions/fork-pr-contributor-approval" -f approval_policy=all_external_contributors >/dev/null \
    && echo "  pull requests from outside contributors wait for your approval before running" \
    || echo "  (couldn't set fork approval; set it in Settings → Actions → General)"

echo "--- Security"
api -X PATCH "repos/$REPO" --input - >/dev/null <<'JSON' && echo "  secret scanning and push protection on"
{"security_and_analysis": {"secret_scanning": {"status": "enabled"}, "secret_scanning_push_protection": {"status": "enabled"}}}
JSON
api -X PUT "repos/$REPO/vulnerability-alerts" >/dev/null && echo "  Dependabot alerts on"
api -X PUT "repos/$REPO/automated-security-fixes" >/dev/null && echo "  Dependabot security fixes on"
api -X PUT "repos/$REPO/private-vulnerability-reporting" >/dev/null && echo "  private vulnerability reporting on"

echo "--- Tidy"
gh repo edit "$REPO" --enable-projects=false --enable-wiki=false --enable-issues=true --delete-branch-on-merge >/dev/null \
    && echo "  Projects and Wiki off, Issues on, merged branches deleted"

echo
echo "Done. Check it any time: tools/github_launch.sh --check"
