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

Each source release dispatches an event containing identifiers. The receiver treats that payload as untrusted. It maps each event to one exact source repository, fetches the release by numeric ID, requires a published immutable stable release, resolves annotated or lightweight tags to the supplied source commit, and retrieves all assets by API asset ID. It also runs GitHub CLI release and per-asset attestation verification. It requires exactly four `tar.gz` archives, two `.deb` files, two `.pkg.tar.zst` files, and `checksums.txt`. Every asset must be uploaded, bounded in size, and have a GitHub SHA-256 digest matching the downloaded bytes and checksum manifest. Archive paths, expansion sizes, executable formats and architectures, completions, native package paths, and exact dependency sets are validated before output is produced.

[`manifests/releases.json`](manifests/releases.json) retains the current and previous immutable release identity for each tool. Every accepted dispatch checks out the latest default-branch manifest when its serialized run starts, carries that exact base SHA to the commit job, re-downloads and verifies every retained release, rebuilds the complete repositories, and stages one Pages artifact. Two events created at the same earlier SHA therefore apply in sequence to the newest committed manifest. A concurrent human update makes the commit stop without mutation; rerunning safely reconstructs from the new head. The published Pages artifact is never used as input. Exact replays succeed without a change; a downgrade or different content at the same version fails. One shared concurrency group serializes release ingestion and cask autobumps.

APT publishes `stable/main`, `Packages`/`Packages.gz`, SHA-256 by-hash copies, and dated `Release`, `InRelease`, and `Release.gpg` files with a seven-day validity window. A daily scheduled reconstruction refreshes that window. Pacman’s standard `repo-add` builds real package and file databases for `x86_64` and `aarch64`; every package and database has a detached signature, and Pages-compatible short database names are regular files. Only the current and previous version per tool are retained, and a final file-type allowlist enforces a 900 MiB deployment ceiling.

## Signing bootstrap and recovery

Create a dedicated package-signing subkey on an offline machine. Do not reuse a personal signing key. Export its secret material, base64 encode it without line wrapping, and configure these values in the protected `package-signing` environment:

- Secret `PACKAGES_GPG_PRIVATE_KEY_B64`: base64 of the exported secret key.
- Secret `PACKAGES_GPG_PASSPHRASE`: the subkey passphrase.
- Variable `PACKAGES_GPG_FINGERPRINT`: the exact 40-character uppercase fingerprint selected for signing.

Signing uses two isolated protected-environment jobs. The first signs opaque package bytes and exits. A separate job with no private-key environment runs `repo-add` over the packages and detached signatures. The final protected job imports the key into a new mode-0700 keyring and signs only the resulting APT and Pacman metadata. Each signing process checks the exact signing-subkey fingerprint, selects it with GPG’s `FINGERPRINT!` syntax, verifies `VALIDSIG` against that same fingerprint, exports only public certificates, and destroys its temporary keyring.

For rotation, first import the old secret key and new public key in the encoded key bundle, keep the old signing-subkey fingerprint selected, publish the combined public keyring with a manual workflow run, and have clients refresh it. Then replace the bundle with the new secret key plus both public keys, select the new signing-subkey fingerprint, and publish again. Keep the offline old key and the last known-good manifest for recovery. If signing or Pages deployment fails, fix the environment and run the workflow manually; it reconstructs the site from immutable retained releases.

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
