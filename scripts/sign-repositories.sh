#!/usr/bin/env bash
set -euo pipefail

mode=${1:?usage: sign-repositories.sh packages|metadata SITE}
site=${2:?usage: sign-repositories.sh packages|metadata SITE}
if [ "$mode" != packages ] && [ "$mode" != metadata ]; then
  echo "mode must be packages or metadata" >&2
  exit 1
fi
: "${PACKAGES_GPG_PRIVATE_KEY_B64:?missing PACKAGES_GPG_PRIVATE_KEY_B64}"
: "${PACKAGES_GPG_PASSPHRASE:?missing PACKAGES_GPG_PASSPHRASE}"
: "${PACKAGES_GPG_FINGERPRINT:?missing PACKAGES_GPG_FINGERPRINT}"

case "$PACKAGES_GPG_FINGERPRINT" in
  (*[!0-9A-F]*|'') echo "PACKAGES_GPG_FINGERPRINT must be uppercase hex" >&2; exit 1 ;;
esac
if [ "${#PACKAGES_GPG_FINGERPRINT}" -ne 40 ]; then
  echo "PACKAGES_GPG_FINGERPRINT must contain 40 hex characters" >&2
  exit 1
fi

export GNUPGHOME
GNUPGHOME=$(mktemp -d)
chmod 700 "$GNUPGHOME"
key_file=$(mktemp)
cleanup() {
  rm -f "$key_file"
  rm -rf "$GNUPGHOME"
}
trap cleanup EXIT

python3 - "$key_file" <<'PY'
import base64, binascii, os, pathlib, sys
try:
    raw = base64.b64decode(os.environ["PACKAGES_GPG_PRIVATE_KEY_B64"], validate=True)
except binascii.Error as exc:
    raise SystemExit(f"invalid base64 private key: {exc}")
pathlib.Path(sys.argv[1]).write_bytes(raw)
PY
gpg --batch --quiet --import "$key_file"
if ! gpg --batch --with-colons --list-secret-keys --fingerprint | awk -F: '$1 == "fpr" { print $10 }' | grep -Fxq "$PACKAGES_GPG_FINGERPRINT"; then
  echo "imported signing key fingerprint does not match configuration" >&2
  exit 1
fi

sign_detached() {
  local input=$1
  local output=$2
  shift 2
  rm -f "$output"
  printf '%s\n' "$PACKAGES_GPG_PASSPHRASE" | gpg --batch --yes --pinentry-mode loopback \
    --passphrase-fd 0 --local-user "$PACKAGES_GPG_FINGERPRINT!" --detach-sign "$@" --output "$output" "$input"
  verify_exact "$output" "$input"
}

verify_exact() {
  local signature=$1
  local input=${2:-}
  local valid
  if [ -n "$input" ]; then
    valid=$(gpg --batch --status-fd 1 --verify "$signature" "$input" 2>/dev/null | awk '$2 == "VALIDSIG" { print $3; exit }')
  else
    valid=$(gpg --batch --status-fd 1 --verify "$signature" 2>/dev/null | awk '$2 == "VALIDSIG" { print $3; exit }')
  fi
  if [ "$valid" != "$PACKAGES_GPG_FINGERPRINT" ]; then
    echo "signature was not made by the configured signing subkey" >&2
    exit 1
  fi
}

if [ "$mode" = packages ]; then
  while IFS= read -r -d '' package; do
    sign_detached "$package" "$package.sig"
  done < <(find "$site/pacman" -type f -name '*.pkg.tar.zst' -print0 | sort -z)
else
  release="$site/apt/dists/stable/Release"
  rm -f "$site/apt/dists/stable/InRelease" "$site/apt/dists/stable/Release.gpg"
  printf '%s\n' "$PACKAGES_GPG_PASSPHRASE" | gpg --batch --yes --pinentry-mode loopback \
    --passphrase-fd 0 --local-user "$PACKAGES_GPG_FINGERPRINT!" --clearsign \
    --output "$site/apt/dists/stable/InRelease" "$release"
  verify_exact "$site/apt/dists/stable/InRelease"
  sign_detached "$release" "$site/apt/dists/stable/Release.gpg" --armor

  while IFS= read -r -d '' database; do
    sign_detached "$database" "$database.sig"
    short=${database%.tar.gz}
    cp "$database" "$short"
    cp "$database.sig" "$short.sig"
  done < <(find "$site/pacman" -type f \( -name 'wawrzdev.db.tar.gz' -o -name 'wawrzdev.files.tar.gz' \) -print0 | sort -z)
fi

mkdir -p "$site/keys"
gpg --batch --export > "$site/keys/wawrzdev-packages.gpg"
gpg --batch --armor --export > "$site/keys/wawrzdev-packages.asc"
if find "$site" -type l -print -quit | grep -q .; then
  echo "Pages tree contains a symbolic link" >&2
  exit 1
fi
