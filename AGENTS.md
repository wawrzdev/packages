# Repository agent instructions

`AGENTS.md` is canonical. `CLAUDE.md` is a relative symlink to it; edit this file
without replacing the symlink. Use the canonical `wawrzdev/packages` repository and
checkout name; `homebrew-tap` is its retired name.

## Ownership and release flow

Read [Release architecture](README.md#release-architecture),
[Live installation verification](README.md#live-installation-verification), and
[Signing bootstrap and recovery](README.md#signing-bootstrap-and-recovery) before
release or distribution work. The workflows and scripts implement those contracts.

- `secret`, `snip`, and `wtf` source repositories own their code, binaries,
  completions, native packages, version tags and immutable GitHub releases. This
  repository owns distribution formulas, the retained release manifest, signed
  package indexes and Pages publication.
- For a source release, follow that CLI's `docs/releasing.md`. Review/merge the
  source with passing checks, then create the stable version tag on the exact
  merged commit. The tag-triggered workflow builds artifacts, uploads a draft,
  verifies uploaded bytes/checksums and release identity, and only then publishes.
  Let that workflow publish; do not manually publish an empty/incomplete release
  with `gh release create` or replace immutable assets. Tag creation can use
  standard Git or `gh api`; the publishing/verification contract is the same.
- Source publication dispatches a hint here. `release-proposals.yml` reconciles
  authoritative immutable releases, validates assets and formulas, and opens a
  manifest/formula PR with rebase auto-merge after required checks. Preserve that
  validation path; do not bypass it by editing versions/checksums from an event
  payload or pushing the default branch directly.
- A merged package proposal triggers `publish-release.yml`, which rebuilds,
  signs and deploys from the merged manifest. A successful source release or
  proposal is not proof that the production package repository has published it.
  Confirm the manifest/formula version and successful publication before dependent
  configuration rollout. Use `verify-production-install.yml` for a real package
  installation check; its ARM64 coverage verifies retrieval/metadata, not execution.
- For recovery, inspect the failed stage and use the documented reconciliation or
  publication retry. Preserve failed drafts for diagnosis; do not move published
  tags, rebuild immutable assets, bypass signatures, or create duplicate runs while
  an authoritative run is still active.

## Changes and validation

Use task branches and ordinary PRs, retaining the repository's rebase-only linear
history. Respect the user's commit, push, merge, release and live-install scope.
Keep account data and signing secrets out of sources and logs. Follow README's
Development commands for code changes; verify instruction links and the relative
symlink for documentation-only changes. Report source validation, publication and
live installation as separate results.
