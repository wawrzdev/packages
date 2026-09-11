#!/usr/bin/env bash
# Auto-bump the personal casks. Detects new upstream versions and rewrites version + sha256.
# Runs in CI (see .github/workflows/autobump.yml) or locally.
# Deps: curl, jq, sha256sum/shasum — no `gh` needed (portable to any minimal runner).
set -euo pipefail
cd "$(dirname "$0")/.."

sha256cmd() {
  if command -v sha256sum >/dev/null; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}
cur_version() { grep -oE 'version "[^"]+"' "$1" | head -1 | sed -E 's/version "([^"]+)"/\1/'; }
gh_api() { # GET a GitHub REST URL, authenticated when GH_TOKEN is set (avoids low anon rate limits)
  if [ -n "${GH_TOKEN:-}" ]; then
    curl -fsSL -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" "$1"
  else
    curl -fsSL -H "Accept: application/vnd.github+json" "$1"
  fi
}
changed=0
valid_version() { [[ "$1" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; }
valid_sha256() { [[ "$1" =~ ^[0-9a-f]{64}$ ]]; }

# ---------- nuvio: GitHub Releases; sha256 straight from the API asset digests ----------
n_rel=$(gh_api "https://api.github.com/repos/NuvioMedia/NuvioDesktop/releases/latest")
n_latest=$(printf '%s' "$n_rel" | jq -r '.tag_name')
n_cur=$(cur_version Casks/nuvio.rb)
if [ "$n_latest" != "$n_cur" ]; then
  if ! valid_version "$n_latest"; then echo "nuvio: invalid upstream version" >&2; exit 1; fi
  echo "nuvio: $n_cur -> $n_latest"
  if ! printf '%s' "$n_rel" | jq -e '[.assets[]|select(.state == "uploaded" and (.name|test("arm64.*\\.dmg$")))]|length == 1' >/dev/null ||
     ! printf '%s' "$n_rel" | jq -e '[.assets[]|select(.state == "uploaded" and (.name|test("x86_64.*\\.dmg$")))]|length == 1' >/dev/null; then
    echo "nuvio: expected exactly one uploaded DMG per architecture" >&2; exit 1
  fi
  n_arm=$(printf '%s' "$n_rel"   | jq -r '.assets[]|select(.state == "uploaded" and (.name|test("arm64.*\\.dmg$")))|.digest|sub("^sha256:"; "")')
  n_intel=$(printf '%s' "$n_rel" | jq -r '.assets[]|select(.state == "uploaded" and (.name|test("x86_64.*\\.dmg$")))|.digest|sub("^sha256:"; "")')
  if valid_sha256 "$n_arm" && valid_sha256 "$n_intel"; then
    sed -i.bak -E "s/version \"[^\"]+\"/version \"$n_latest\"/"           Casks/nuvio.rb
    sed -i.bak -E "s/(arm:[[:space:]]+)\"[0-9a-f]{64}\"/\1\"$n_arm\"/"     Casks/nuvio.rb
    sed -i.bak -E "s/(intel:[[:space:]]+)\"[0-9a-f]{64}\"/\1\"$n_intel\"/" Casks/nuvio.rb
    rm -f Casks/nuvio.rb.bak; changed=1
  else
    echo "nuvio: invalid digests" >&2; exit 1
  fi
fi

# ---------- graphite: S3 electron-updater manifest; sha256 needs a download ----------
G_BASE="https://system-tray-app-releases-prod.s3.us-west-2.amazonaws.com"
g_latest=$(curl -fsSL "$G_BASE/latest-mac.yml" | awk '/^version:/{print $2; exit}')
g_cur=$(cur_version Casks/graphite.rb)
if [ -n "$g_latest" ] && [ "$g_latest" != "$g_cur" ]; then
  if ! valid_version "$g_latest"; then echo "graphite: invalid upstream version" >&2; exit 1; fi
  echo "graphite: $g_cur -> $g_latest"
  tmp=$(mktemp)
  curl -fsSL "$G_BASE/Graphite-${g_latest}-universal.dmg" -o "$tmp"
  g_sha=$(sha256cmd "$tmp"); rm -f "$tmp"
  if ! valid_sha256 "$g_sha"; then echo "graphite: invalid artifact checksum" >&2; exit 1; fi
  sed -i.bak -E "s/version \"[^\"]+\"/version \"$g_latest\"/"    Casks/graphite.rb
  sed -i.bak -E "s/sha256 \"[0-9a-f]{64}\"/sha256 \"$g_sha\"/"   Casks/graphite.rb
  rm -f Casks/graphite.rb.bak; changed=1
fi

if [ "$changed" = 1 ]; then
  echo "casks_changed=true" >> "${GITHUB_OUTPUT:-/dev/stdout}"
else
  echo "no cask updates"; echo "casks_changed=false" >> "${GITHUB_OUTPUT:-/dev/stdout}"
fi
