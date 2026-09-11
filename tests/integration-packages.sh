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
  --quick-gen-key "Package CI <packages@example.invalid>" rsa2048 cert 1d
primary=$(gpg --batch --with-colons --list-secret-keys --fingerprint | awk -F: '$1 == "fpr" { print $10; exit }')
gpg --batch --pinentry-mode loopback --passphrase test-pass --quick-add-key "$primary" rsa2048 sign 1d
signer=$(gpg --batch --with-colons --list-secret-keys --fingerprint | awk -F: '$1 == "fpr" { value=$10 } END { print value }')
gpg --batch --pinentry-mode loopback --passphrase test-pass --export-secret-keys > "$test_root/secret.gpg"
export PACKAGES_GPG_PRIVATE_KEY_B64
PACKAGES_GPG_PRIVATE_KEY_B64=$(base64 -w0 "$test_root/secret.gpg")
export PACKAGES_GPG_PASSPHRASE=test-pass
export PACKAGES_GPG_FINGERPRINT="$signer"
unset GNUPGHOME

bash scripts/sign-repositories.sh "$test_root/site"
python3 scripts/validate_site.py "$test_root/site"

python3 -m http.server 18080 --bind 127.0.0.1 --directory "$test_root/site" >"$test_root/http.log" 2>&1 &
server_pid=$!
for _ in {1..20}; do
  if curl -fsS http://127.0.0.1:18080/keys/wawrzdev-packages.gpg >/dev/null; then break; fi
  sleep 0.25
done

sudo cp "$test_root/site/keys/wawrzdev-packages.gpg" "$apt_key"
printf '%s\n' "deb [arch=amd64 signed-by=$apt_key] http://127.0.0.1:18080/apt stable main" | sudo tee "$apt_source" >/dev/null
sudo apt-get update -o Dir::Etc::sourcelist="$apt_source" -o Dir::Etc::sourceparts="-" \
  -o APT::Get::List-Cleanup="0"
mkdir "$test_root/apt-download"
(cd "$test_root/apt-download" && apt-get download secret)
test -s "$test_root/apt-download/secret_1.2.3_linux_amd64.deb"
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
sed "s|@ROOT@|$test_root|g" tests/pacman-ci.conf > "$test_root/pacman.conf"
pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" --noconfirm -Sy
pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" --noconfirm -Sw secret
pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" -Fl secret | grep -F 'secret usr/bin/secret'

printf 'tamper' >> "$test_root/site/pacman/x86_64/secret_1.2.3_linux_amd64.pkg.tar.zst"
rm -f "$test_root/pacman-cache"/*
if pacman --config "$test_root/pacman.conf" --root "$test_root/pacman-root" --dbpath "$test_root/pacman-db" --noconfirm -Sw secret; then
  echo "pacman accepted a tampered package" >&2
  exit 1
fi
