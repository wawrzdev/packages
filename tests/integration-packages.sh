#!/usr/bin/env bash
set -euo pipefail

test_root=$(mktemp -d)
apt_source=/etc/apt/sources.list.d/wawrzdev-packages-test.list
apt_key=/usr/share/keyrings/wawrzdev-packages-test.gpg
server_pid=
cleanup() {
  if [ -n "$server_pid" ]; then kill "$server_pid" 2>/dev/null || true; fi
  sudo rm -f "$apt_source" "$apt_key"
  rm -rf "$test_root"
}
trap cleanup EXIT

corrupt_file() {
  python3 - "$1" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
data = bytearray(path.read_bytes())
data[len(data) // 2] ^= 1
path.write_bytes(data)
PY
}

python3 - "$test_root" <<'PY'
import importlib.util, pathlib, sys, time
root = pathlib.Path.cwd()
spec = importlib.util.spec_from_file_location("fixtures", root / "tests/test_publish_release.py")
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixtures
spec.loader.exec_module(fixtures)
base = pathlib.Path(sys.argv[1])
source = base / "source"
source.mkdir()
release = fixtures.release_fixture(source)
fixtures.publisher.publish([release], base / "site", int(time.time()))
PY

while IFS= read -r -d '' package; do
  mv "$package" "$package.tar"
  zstd -q "$package.tar" -o "$package"
  rm -f "$package.tar"
done < <(find "$test_root/site/pacman" -name '*.pkg.tar.zst' -print0)

export GNUPGHOME="$test_root/keygen"
mkdir -m 700 "$GNUPGHOME"
gpg --batch --pinentry-mode loopback --passphrase test-pass \
  --quick-gen-key "Package CI <packages@example.invalid>" ed25519 cert 1d
primary=$(gpg --batch --with-colons --list-secret-keys --fingerprint | awk -F: '$1 == "fpr" { print $10; exit }')
gpg --batch --pinentry-mode loopback --passphrase test-pass --quick-add-key "$primary" ed25519 sign 1d
signer=$(gpg --batch --with-colons --list-secret-keys --fingerprint | awk -F: '$1 == "fpr" { value=$10 } END { print value }')
gpg --batch --pinentry-mode loopback --passphrase test-pass --export-secret-keys > "$test_root/secret.gpg"
export PACKAGES_GPG_PRIVATE_KEY_B64
PACKAGES_GPG_PRIVATE_KEY_B64=$(base64 -w0 "$test_root/secret.gpg")
export PACKAGES_GPG_PASSPHRASE=test-pass
export PACKAGES_GPG_FINGERPRINT="$signer"
unset GNUPGHOME

bash scripts/sign-repositories.sh packages "$test_root/site"
unset PACKAGES_GPG_PRIVATE_KEY_B64 PACKAGES_GPG_PASSPHRASE PACKAGES_GPG_FINGERPRINT
bash scripts/build-pacman-repositories.sh "$test_root/site"
export PACKAGES_GPG_PRIVATE_KEY_B64
PACKAGES_GPG_PRIVATE_KEY_B64=$(base64 -w0 "$test_root/secret.gpg")
export PACKAGES_GPG_PASSPHRASE=test-pass
export PACKAGES_GPG_FINGERPRINT="$signer"
bash scripts/sign-repositories.sh metadata "$test_root/site"
python3 scripts/validate_site.py "$test_root/site"
keyring="$test_root/site/keys/wawrzdev-packages.gpg"
gpgv --keyring "$keyring" "$test_root/site/apt/dists/stable/InRelease"
gpgv --keyring "$keyring" "$test_root/site/apt/dists/stable/Release.gpg" "$test_root/site/apt/dists/stable/Release"
while IFS= read -r -d '' signature; do
  gpgv --keyring "$keyring" "$signature" "${signature%.sig}"
done < <(find "$test_root/site/pacman" -type f -name '*.sig' -print0)

python3 -m http.server 18080 --bind 127.0.0.1 --directory "$test_root/site" >"$test_root/http.log" 2>&1 &
server_pid=$!
for _ in {1..20}; do
  if curl -fsS http://127.0.0.1:18080/keys/wawrzdev-packages.gpg >/dev/null; then break; fi
  sleep 0.25
done

sudo cp "$test_root/site/keys/wawrzdev-packages.gpg" "$apt_key"
sudo dpkg --add-architecture arm64
printf '%s\n' "deb [arch=amd64,arm64 signed-by=$apt_key] http://127.0.0.1:18080/apt stable main" | sudo tee "$apt_source" >/dev/null
sudo apt-get update -o Dir::Etc::sourcelist="$apt_source" -o Dir::Etc::sourceparts="-" \
  -o APT::Get::List-Cleanup="0"
mkdir "$test_root/apt-download"
(cd "$test_root/apt-download" && apt-get download secret)
(cd "$test_root/apt-download" && apt-get download secret:arm64)
test -s "$test_root/apt-download/secret_1.2.3_linux_amd64.deb"
test -s "$test_root/apt-download/secret_1.2.3_linux_arm64.deb"

expect_apt_update_failure() {
  local label=$1
  shift
  local lists="$test_root/apt-lists-$label"
  sudo mkdir -p "$lists/partial"
  if sudo apt-get update -o Dir::Etc::sourcelist="$apt_source" -o Dir::Etc::sourceparts="-" \
    -o Dir::State::lists="$lists" -o APT::Update::Error-Mode=any "$@"; then
    echo "apt accepted tampered $label metadata" >&2
    exit 1
  fi
}

cp "$test_root/site/apt/dists/stable/InRelease" "$test_root/InRelease.good"
corrupt_file "$test_root/site/apt/dists/stable/InRelease"
expect_apt_update_failure inrelease
cp "$test_root/InRelease.good" "$test_root/site/apt/dists/stable/InRelease"

mv "$test_root/site/apt/dists/stable/InRelease" "$test_root/InRelease.hidden"
cp "$test_root/site/apt/dists/stable/Release.gpg" "$test_root/Release.gpg.good"
corrupt_file "$test_root/site/apt/dists/stable/Release.gpg"
expect_apt_update_failure release-signature
cp "$test_root/Release.gpg.good" "$test_root/site/apt/dists/stable/Release.gpg"
mv "$test_root/InRelease.hidden" "$test_root/site/apt/dists/stable/InRelease"

packages_index="$test_root/site/apt/dists/stable/main/binary-amd64/Packages"
cp "$packages_index" "$test_root/Packages.good"
printf 'tamper' >> "$packages_index"
expect_apt_update_failure packages -o Acquire::By-Hash=false -o Acquire::CompressionTypes::Order::=uncompressed
cp "$test_root/Packages.good" "$packages_index"

while IFS= read -r -d '' by_hash; do
  printf 'tamper' >> "$by_hash"
done < <(find "$test_root/site/apt/dists/stable/main/binary-amd64/by-hash" -type f -print0)
expect_apt_update_failure by-hash

printf 'tamper' >> "$test_root/site/apt/pool/main/s/secret/secret_1.2.3_linux_amd64.deb"
rm -f "$test_root/apt-download"/*.deb
if (cd "$test_root/apt-download" && apt-get download secret); then
  echo "apt accepted a tampered package" >&2
  exit 1
fi

mkdir -p "$test_root/pacman-root" "$test_root/pacman-db" "$test_root/pacman-cache" "$test_root/pacman-gpg"
chmod 700 "$test_root/pacman-gpg"
pacman-key --gpgdir "$test_root/pacman-gpg" --init
pacman-key --gpgdir "$test_root/pacman-gpg" --add "$test_root/site/keys/wawrzdev-packages.gpg"
pacman-key --gpgdir "$test_root/pacman-gpg" --lsign-key "$signer"
sed -e "s|@ROOT@|$test_root|g" -e 's|@ARCH@|x86_64|g' tests/pacman-ci.conf > "$test_root/pacman.conf"
pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" --noconfirm -Sy
pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" --noconfirm -Sw secret
pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" -Fl secret | grep -F 'secret usr/bin/secret'
pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" -Fy
pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" -F usr/bin/secret | grep -F secret

mkdir -p "$test_root/pacman-arm-root" "$test_root/pacman-arm-db" "$test_root/pacman-arm-cache"
sed -e "s|@ROOT@|$test_root|g" -e 's|@ARCH@|aarch64|g' \
  -e "s|pacman-cache|pacman-arm-cache|g" tests/pacman-ci.conf > "$test_root/pacman-arm.conf"
pacman --config "$test_root/pacman-arm.conf" --root "$test_root/pacman-arm-root" --dbpath "$test_root/pacman-arm-db" --noconfirm -Sy
pacman --config "$test_root/pacman-arm.conf" --root "$test_root/pacman-arm-root" --dbpath "$test_root/pacman-arm-db" --noconfirm -Sw secret
test -s "$test_root/pacman-arm-cache/secret_1.2.3_linux_arm64.pkg.tar.zst"

expect_pacman_sync_failure() {
  local label=$1
  rm -f "$test_root/pacman-db/sync/wawrzdev.db" "$test_root/pacman-db/sync/wawrzdev.db.sig"
  if pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" --noconfirm -Sy; then
    echo "pacman accepted tampered $label" >&2
    exit 1
  fi
}

database="$test_root/site/pacman/x86_64/wawrzdev.db"
database_signature="$database.sig"
cp "$database" "$test_root/wawrzdev.db.good"
cp "$database_signature" "$test_root/wawrzdev.db.sig.good"
corrupt_file "$database"
expect_pacman_sync_failure database
cp "$test_root/wawrzdev.db.good" "$database"
corrupt_file "$database_signature"
expect_pacman_sync_failure database-signature
cp "$test_root/wawrzdev.db.sig.good" "$database_signature"

package_signature="$test_root/site/pacman/x86_64/secret_1.2.3_linux_amd64.pkg.tar.zst.sig"
cp "$package_signature" "$test_root/package.sig.good"
corrupt_file "$package_signature"
if gpgv --keyring "$keyring" "$package_signature" "${package_signature%.sig}"; then
  echo "gpgv accepted a tampered package signature" >&2
  exit 1
fi
cp "$test_root/package.sig.good" "$package_signature"

printf 'tamper' >> "$test_root/site/pacman/x86_64/secret_1.2.3_linux_amd64.pkg.tar.zst"
rm -f "$test_root/pacman-cache"/*
if pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" --noconfirm -Sw secret; then
  echo "pacman accepted a tampered package" >&2
  exit 1
fi
