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

Repositories are published through GitHub Actions Pages. The primary public certificate fingerprint is
`CA9E472DA65EAAC61A29DF2C6BC9CD87B018E5C9`. Verify the downloaded certificate against this fingerprint
before trusting it. The current signing subkey is `3B4493F499C7D2EC0F8965DC410405C255323B8C`, expiring
September 11, 2027. Clients trust the primary certificate; signature diagnostics identify the signing subkey.
Authenticate every primary fingerprint in a downloaded keyring, including any additional certificate
introduced during rotation; do not accept unexpected primary keys merely because the current one is present.

Debian/Ubuntu (`amd64` and `arm64`):

```sh
curl -fsSL https://wawrzdev.github.io/packages/keys/wawrzdev-packages.gpg \
  -o /tmp/wawrzdev-packages.gpg
gpg --show-keys --with-fingerprint /tmp/wawrzdev-packages.gpg
# Check the primary fingerprint above before installing the certificate.
sudo install -m 0644 /tmp/wawrzdev-packages.gpg /usr/share/keyrings/wawrzdev-packages.gpg
echo "deb [signed-by=/usr/share/keyrings/wawrzdev-packages.gpg] https://wawrzdev.github.io/packages/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/wawrzdev-packages.list
sudo apt update
sudo apt install secret snip wtf
```

Arch Linux (`x86_64` and `aarch64`):

```sh
curl -fsSL https://wawrzdev.github.io/packages/keys/wawrzdev-packages.asc -o /tmp/wawrzdev-packages.asc
gpg --show-keys --with-fingerprint /tmp/wawrzdev-packages.asc
# Check the primary fingerprint above before importing the certificate.
sudo pacman-key --add /tmp/wawrzdev-packages.asc
sudo pacman-key --lsign-key CA9E472DA65EAAC61A29DF2C6BC9CD87B018E5C9
```

Then add this section to `/etc/pacman.conf` and run `sudo pacman -Syu`:

```ini
[wawrzdev]
SigLevel = Required DatabaseRequired
Server = https://wawrzdev.github.io/packages/pacman/$arch
```

## Release architecture

The source repositories own source code, binaries, completions, native packages, and GitHub releases. This repository owns Homebrew formulas, the retained release manifest, package indexes, and repository signatures.

Source releases send untrusted dispatch hints. The proposal workflow checks the event/repository allowlist, then reconciles the authoritative latest final release from **all three** source repositories. Scheduled reconciliation also recovers a missed or replaced dispatch. It requires immutable stable releases, resolves their tags, retrieves assets by API ID, and verifies GitHub release/per-asset attestations. The exact four archives, two Debian packages, two Arch packages, and checksum file must satisfy digest, size, path, architecture, completion, and dependency checks. A missing first release is expected during bootstrap; downgrades and changed identities at the same version fail.

[`manifests/releases.json`](manifests/releases.json) retains the current and previous **merged** release identity for each tool. [`release-proposals.yml`](.github/workflows/release-proposals.yml) validates the proposed native packages and Homebrew formulas without write credentials or signing keys. A separate environment-bound `propose` job opens a manifest/formula PR and requests rebase auto-merge after required CI and conversation checks pass. Both updaters use [`open-update-pr.sh`](scripts/open-update-pr.sh) for the shared PR logic. These remain ordinary jobs so environment secrets resolve without broad secret inheritance; see [actions/runner#4453](https://github.com/actions/runner/issues/4453). Neither updater pushes the default branch.

The writer checks that the validated base is still current and uses a new `automation/<kind>/<base>-<tree>` branch with a normal push. Replays reuse the exact branch head; superseded PRs with our own automation marker are closed. It never force-pushes or deletes branches, and leaves an explicitly closed exact proposal closed. Default-branch pushes trigger fresh reconciliation, so strict up-to-date checks can be satisfied by a new proposal after another merge. The shared proposal concurrency group serializes preparation/writing; daily runs provide recovery when GitHub replaces a pending run. A failed validation or changed base leaves the default branch untouched; rerun the proposal workflow after resolving it.

[`publish-release.yml`](.github/workflows/publish-release.yml) runs only for the default branch, manually or after a merge, plus daily for metadata refresh. It checks out the latest merged manifest when its own serialized run starts, re-downloads and re-verifies every retained release, rebuilds the complete repositories, and stages one signed Pages artifact. It has no source-write permission, never consumes a PR artifact, and checks that its default-branch snapshot is still current before uploading the deployment. A superseded run stops; the pending newer run or a manual retry rebuilds from current merged state. The published Pages artifact is never used as input.

APT publishes `stable/main`, `Packages`/`Packages.gz`, SHA-256 by-hash copies, and dated `Release`, `InRelease`, and `Release.gpg` files with a seven-day validity window. A daily scheduled reconstruction refreshes that window. Pacman’s standard `repo-add` builds real package and file databases for `x86_64` and `aarch64`; every package and database has a detached signature, and Pages-compatible short database names are regular files. Only the current and previous version per tool are retained, and a final file-type allowlist enforces a 900 MiB deployment ceiling.

## Live installation verification

After a release appears in the published package repository, run
[`verify-production-install.yml`](.github/workflows/verify-production-install.yml) with
`tool` (`secret`, `snip`, or `wtf`) and `release_tag`. It installs and runs the selected
CLI through Homebrew on macOS/Linux, APT on Ubuntu amd64, and Pacman inside an official
Arch x86_64 container. Native installs resolve declared dependencies through the OS repositories.
Published trust fingerprints and signed indexes/packages are checked throughout.

ARM64 coverage verifies authenticated package retrieval, architecture, and version metadata;
it does not execute ARM64 binaries or install their dependency trees. The manual check is read-only
against the production repository and can run from a review branch before merging harness changes.

## Signing bootstrap and recovery

Create a dedicated certification primary key and package-signing subkey on a trusted personal machine
(offline generation is an option). Back up the primary key, passphrase, and revocation certificate in a
personal recovery vault and verify restoration before removing working recovery copies. Keep the
primary secret key out of CI. Do not reuse a personal signing key. Export only the signing subkey's
secret material, base64 encode it without line wrapping, and configure these values in the protected
`package-signing` environment:

- Secret `PACKAGES_GPG_PRIVATE_KEY_B64`: base64 of the exported secret key.
- Secret `PACKAGES_GPG_PASSPHRASE`: the subkey passphrase.
- Variable `PACKAGES_GPG_FINGERPRINT`: the exact 40-character uppercase fingerprint selected for signing.

Signing uses two isolated protected-environment jobs. The first signs opaque package bytes and exits. A separate job with no private-key environment runs `repo-add` over the packages and detached signatures. The final protected job imports the key into a new mode-0700 keyring and signs only the resulting APT and Pacman metadata. Each signing process checks the exact signing-subkey fingerprint, selects it with GPG’s `FINGERPRINT!` syntax, verifies `VALIDSIG` against that same fingerprint, exports only public certificates, and destroys its temporary keyring.

For rotation, first import the old secret key and new public key in the encoded key bundle, keep the old signing-subkey fingerprint selected, publish the combined public keyring with a manual workflow run, and have clients refresh it. Then replace the bundle with the new secret key plus both public keys, select the new signing-subkey fingerprint, and publish again. Keep the offline old key and the last known-good manifest for recovery. If signing or Pages deployment fails, fix the environment and run the workflow manually; it reconstructs the site from immutable retained releases.

Before activating update automation or the first CLI tag:

1. Merge these workflows to the default branch. Require PRs, passing `test`, `homebrew-macos`, and `homebrew-linux` checks with up-to-date branches, resolved conversations, and linear history. Require zero external approvals; disallow force pushes and deletion of the default branch. Do not grant the automation App a bypass.
2. Enable repository auto-merge and allow **rebase merges only**. Configure protections before running update automation: auto-merge can merge immediately if no requirements exist.
3. Register a dedicated GitHub App installed only on `wawrzdev/packages`, with repository **Contents: read/write** and **Pull requests: read/write**. No Actions, administration, Pages, or signing access is needed. In the `package-updates` environment, restricted to the default branch, set variable `PACKAGES_APP_CLIENT_ID` and secret `PACKAGES_APP_PRIVATE_KEY` (the PEM key). No required environment reviewer is needed for unattended updates.
4. Enable immutable releases in `secret`, `snip`, and `wtf`. Each producer uses a separate `package-dispatch` environment restricted to `v*` tags, with variable `PACKAGES_APP_CLIENT_ID` and secret `PACKAGES_APP_PRIVATE_KEY`. Its checkout-free notification job mints a short-lived token for `wawrzdev/packages` with Contents write only, after validating the published immutable release. The App installation remains limited to `packages`; a personal dispatch token is not needed.
5. Protect the `package-signing` environment and configure its secrets and fingerprint variable. Enable Pages with GitHub Actions as its source and protect the `github-pages` environment. Restrict both environments to the default branch.
6. Run a proposal through required CI and auto-merge, then verify publication and installation on both architectures. The initial no-release bootstrap produces an empty signed repository without inventing package versions.

The pinned official App-token action mints a token restricted to this repository and the two write permissions only in the PR-writing job, then revokes it on completion. No App secret/token is available to source validation, Homebrew execution, native package parsing, or publication. GitHub's built-in `GITHUB_TOKEN` is deliberately read-only in those jobs. Its automated PR events require manual workflow approval and its pushes do not start ordinary workflows; the dedicated App allows unattended required CI. See [GitHub token event behavior](https://docs.github.com/en/actions/concepts/security/github_token#when-github_token-triggers-workflow-runs) and the [official App-token action](https://github.com/actions/create-github-app-token).

Changing the default branch may require existing clones to run `git remote set-head origin -a`; Homebrew users can run `brew tap --repair`.

## Existing casks

`Casks/nuvio.rb` and `Casks/graphite.rb` remain auto-updated daily by [`scripts/bump-casks.sh`](scripts/bump-casks.sh). The updater validates upstream versions, asset cardinality, and checksums before proposing a PR; it never commits to the default branch directly. Both casks set `auto_updates true` because the applications also self-update.

## Development

No task runner or `mise` installation is assumed.

```sh
python3 -m unittest discover -s tests -v
bash -n scripts/*.sh
shellcheck scripts/*.sh       # when installed
actionlint                    # when installed
```
