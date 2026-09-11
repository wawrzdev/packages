#!/usr/bin/env bash
# Called only after validation, with an independently approved automation credential.
set -euo pipefail

kind=${1:?usage: open-update-pr.sh releases|casks BASE_SHA}
base=${2:?missing validated base SHA}
: "${GH_TOKEN:?missing PR automation token}"
: "${GITHUB_REPOSITORY:?missing GITHUB_REPOSITORY}"
: "${DEFAULT_BRANCH:?missing DEFAULT_BRANCH}"
case "$kind" in
  releases) paths=(manifests/releases.json Formula); title='packages: update verified releases' ;;
  casks) paths=(Casks); title='casks: update verified upstream versions' ;;
  *) echo 'unsupported update kind' >&2; exit 1 ;;
esac
[[ "$base" =~ ^[0-9a-f]{40}$ ]] || { echo 'invalid base SHA' >&2; exit 1; }
test "$(git rev-parse HEAD)" = "$base"
git diff --cached --quiet
# The credential is read from GH_TOKEN by gh's helper, never embedded in a remote URL.
gh auth setup-git
remote_base=$(git ls-remote origin "refs/heads/$DEFAULT_BRANCH" | cut -f1)
if [ "$remote_base" != "$base" ]; then
  echo 'Default branch changed during preparation; rerun against the new merged state.' >&2
  exit 1
fi
for path in "${paths[@]}"; do
  if [ -e "$path" ]; then git add -- "$path"; fi
done
if git diff --cached --quiet; then
  echo 'No source changes to propose.'
  exit 0
fi

tree=$(git write-tree)
branch="automation/$kind/${base:0:12}-${tree:0:12}"
git config user.name 'packages-automation[bot]'
git config user.email 'wawrz.dev@gmail.com'
git commit -m "$title"
existing=$(git ls-remote origin "refs/heads/$branch" | cut -f1)
if [ -n "$existing" ]; then
  git fetch origin "refs/heads/$branch"
  test "$(git rev-parse 'FETCH_HEAD^{tree}')" = "$tree"
  test "$(git rev-parse 'FETCH_HEAD^')" = "$base"
  head=$existing
else
  head=$(git rev-parse HEAD)
  git push origin "HEAD:refs/heads/$branch"
fi

pr_state=$(gh pr list --repo "$GITHUB_REPOSITORY" --head "$branch" --base "$DEFAULT_BRANCH" \
  --state all --json state --jq '.[0].state // ""')
if [ "$pr_state" = CLOSED ]; then
  echo 'This exact proposal was closed. Leave it closed for human review.' >&2
  exit 1
fi
if [ "$pr_state" = MERGED ]; then
  echo 'This proposal has already merged.'
  exit 0
fi
body=$(mktemp)
trap 'rm -f "$body"' EXIT
printf '<!-- packages-automation:%s -->\n\n%s\n\n%s\n' "$kind" \
  'Generated from verified upstream data against the current default branch.' \
  'Auto-merge uses rebase only after required CI and conversation checks pass. This PR does not publish or access signing keys.' > "$body"
if [ -z "$pr_state" ]; then
  gh pr create --repo "$GITHUB_REPOSITORY" --head "$branch" --base "$DEFAULT_BRANCH" \
    --title "$title" --body-file "$body"
fi
gh pr merge --repo "$GITHUB_REPOSITORY" "$branch" --auto --rebase --match-head-commit "$head"

# The new proposal includes the latest authoritative state. Close only our own marked
# superseded proposals; never force-push, delete branches, or alter unrelated PRs.
gh pr list --repo "$GITHUB_REPOSITORY" --base "$DEFAULT_BRANCH" --state open --limit 100 \
  --json number,headRefName,body,isCrossRepository > "$body"
python3 - "$body" "$kind" "$branch" <<'PY' | while read -r number; do
import json, pathlib, sys
records = json.loads(pathlib.Path(sys.argv[1]).read_text())
kind, current = sys.argv[2:]
for record in records:
    if (not record["isCrossRepository"]
        and record["headRefName"].startswith(f"automation/{kind}/")
        and record["headRefName"] != current
        and record["body"].startswith(f"<!-- packages-automation:{kind} -->")):
        print(record["number"])
PY
  gh pr close --repo "$GITHUB_REPOSITORY" "$number" \
    --comment 'Superseded by the newer verified automation proposal.'
done
