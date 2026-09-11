# wawrzdev packages

Homebrew, APT, and Pacman distribution for `secret`, `snip`, and `wtf`, plus the existing Nuvio and Graphite Homebrew casks.

The repository name is not prefixed with `homebrew-`, so add the tap with its explicit URL:

```sh
brew tap wawrzdev/packages https://github.com/wawrzdev/packages.git
brew install wawrzdev/packages/secret
brew install wawrzdev/packages/snip
brew install wawrzdev/packages/wtf
brew install --cask wawrzdev/packages/nuvio
brew install --cask wawrzdev/packages/graphite
```

Homebrew core also has an unrelated formula named `wtf`. Use the fully qualified `wawrzdev/packages/wtf` name; the two linked executables cannot coexist.

## Linux repositories

Pages must be enabled with **Source: GitHub Actions**. Replace `FINGERPRINT` below with the fingerprint published during repository setup.

Debian/Ubuntu (`amd64` and `arm64`):

```sh
curl -fsSL https://wawrzdev.github.io/packages/keys/wawrzdev-packages.gpg \
  | sudo tee /usr/share/keyrings/wawrzdev-packages.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/wawrzdev-packages.gpg] https://wawrzdev.github.io/packages/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/wawrzdev-packages.list
sudo apt update
sudo apt install secret snip wtf
```

Arch Linux (`x86_64` and `aarch64`):

```sh
curl -fsSL https://wawrzdev.github.io/packages/keys/wawrzdev-packages.asc | gpg --show-keys
curl -fsSL https://wawrzdev.github.io/packages/keys/wawrzdev-packages.asc | sudo pacman-key --add -
sudo pacman-key --lsign-key FINGERPRINT
```

Then add this section to `/etc/pacman.conf` and run `sudo pacman -Syu`:

```ini
[wawrzdev]
SigLevel = Required DatabaseRequired
Server = https://wawrzdev.github.io/packages/pacman/$arch
```

## Release architecture

The source repositories own source code, binaries, completions, native packages, and GitHub releases. This repository owns Homebrew formulas, the retained release manifest, package indexes, and repository signatures.

Each source release dispatches an event containing identifiers. The receiver treats that payload as untrusted. It maps each event to one exact source repository, fetches the release by numeric ID, requires a published immutable stable release, resolves the tag to the supplied full commit SHA, and retrieves all assets by API asset ID. It requires exactly four `tar.gz` archives, two `.deb` files, two `.pkg.tar.zst` files, and `checksums.txt`. Every asset must be uploaded, nonempty, and have a GitHub SHA-256 digest matching the downloaded bytes and checksum manifest. Archive paths and package metadata are validated before output is produced.

[`manifests/releases.json`](manifests/releases.json) retains the current and previous immutable release identity for each tool. Every accepted dispatch re-downloads and verifies every retained release, rebuilds complete deterministic APT and Pacman indexes, and stages one Pages artifact. The published Pages artifact is never used as input. Exact replays succeed without a change; a downgrade or different content at the same version fails. One shared concurrency group serializes release ingestion and cask autobumps.

APT publishes `stable/main`, deterministic `Packages`/`Packages.gz`, SHA-256 by-hash copies, `Release`, `InRelease`, and `Release.gpg`. Pacman publishes repositories for `x86_64` and `aarch64`, detached signatures for every package and database, and regular-file short database names compatible with Pages. Only the current and previous version per tool are retained, keeping the Pages deployment comfortably below its size limit.

## Signing bootstrap and recovery

Create a dedicated package-signing subkey on an offline machine. Do not reuse a personal signing key. Export its secret material, base64 encode it without line wrapping, and configure these values in the protected `package-signing` environment:

- Secret `PACKAGES_GPG_PRIVATE_KEY_B64`: base64 of the exported secret key.
- Secret `PACKAGES_GPG_PASSPHRASE`: the subkey passphrase.
- Variable `PACKAGES_GPG_FINGERPRINT`: the exact 40-character uppercase fingerprint selected for signing.

The signing job creates a mode-0700 temporary keyring, imports the key from a temporary file, checks the exact fingerprint, supplies the passphrase over standard input, verifies all signatures, exports only the public key into the site, and destroys the keyring.

For rotation, first import the new secret key and old public key in the encoded key bundle, keep the old fingerprint selected, publish the combined public keyring with a manual workflow run, and have clients refresh it. Then select the new fingerprint and publish again. Keep the offline old key and the last known-good manifest for recovery. If signing or Pages deployment fails, fix the environment and run the workflow manually; it reconstructs the site from immutable retained releases.

Before the first CLI tag:

1. Make this branch the default branch. Dispatch and scheduled workflows only run from the default branch.
2. Enable immutable releases in `secret`, `snip`, and `wtf` and configure their `PACKAGES_DISPATCH_TOKEN` secrets.
3. Protect the `package-signing` environment and configure its secrets and fingerprint variable.
4. Enable Pages with GitHub Actions as its source and protect the `github-pages` environment.
5. Trigger a test release and verify installation on both architectures.

Changing the default branch may require existing clones to run `git remote set-head origin -a`; Homebrew users can run `brew tap --repair`.

## Existing casks

`Casks/nuvio.rb` and `Casks/graphite.rb` remain auto-updated daily by [`scripts/bump-casks.sh`](scripts/bump-casks.sh). The updater validates upstream versions, asset cardinality, and checksums before editing. Both casks set `auto_updates true` because the applications also self-update.

## Development

No task runner or `mise` installation is assumed.

```sh
python3 -m unittest discover -s tests -v
bash -n scripts/*.sh
shellcheck scripts/*.sh       # when installed
actionlint                    # when installed
```
