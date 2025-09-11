#!/usr/bin/env bash
set -euo pipefail

# Configure branch protection for main using gh CLI.
# Requires: gh authenticated with repo admin access (GH_TOKEN or gh auth login).

OWNER="${OWNER:-JSunRae}"
REPO="${REPO:-Trading}"
BRANCH="${BRANCH:-main}"

here=$(cd "$(dirname "$0")" && pwd)
json="${here}/branch_protection_main.json"

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh CLI not found. Install https://cli.github.com/" >&2
  exit 1
fi

echo "Applying branch protection to ${OWNER}/${REPO}@${BRANCH}..."

# Discover actual check run context names from the latest commit on BRANCH
if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq not found. Please install jq to auto-detect check contexts." >&2
  exit 1
fi

echo "Detecting check runs for latest commit on ${BRANCH}..."
latest_sha=$(gh api -H "Accept: application/vnd.github+json" \
  "/repos/${OWNER}/${REPO}/commits/${BRANCH}" | jq -r .sha)

names=$(gh api -H "Accept: application/vnd.github+json" \
  "/repos/${OWNER}/${REPO}/commits/${latest_sha}/check-runs" | jq -r '.check_runs[].name')

ci_ctx=$(echo "$names" | awk '/^CI / {print; exit}')
smoke_ctx=$(echo "$names" | awk '/^Cross-Repo Smoke/ {print; exit}')

if [[ -z "$ci_ctx" ]]; then
  ci_ctx="CI / test"
fi
if [[ -z "$smoke_ctx" ]]; then
  smoke_ctx="Cross-Repo Smoke (Trading) / consume-tf1-artifact"
fi

tmp_payload=$(mktemp)
jq --arg ci "$ci_ctx" --arg smoke "$smoke_ctx" '
  .required_status_checks.checks = ([{"context": $ci}, {"context": $smoke}] | unique)
' "$json" > "$tmp_payload"

# Apply main protection (status checks, reviews, admins, etc.) with detected contexts
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/${OWNER}/${REPO}/branches/${BRANCH}/protection" \
  --input "$tmp_payload"

rm -f "$tmp_payload"

echo "Enabling required signed commits (if supported)..."
set +e
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  "/repos/${OWNER}/${REPO}/branches/${BRANCH}/protection/required_signatures" >/dev/null 2>&1
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "Note: Could not enable required signed commits via API (insufficient permissions or unsupported)." >&2
fi

echo "Done. Verify in Settings → Branches."
