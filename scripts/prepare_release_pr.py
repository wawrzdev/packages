#!/usr/bin/env python3
"""Reconcile allowlisted source releases into a source-only pull request proposal."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
import urllib.error

from publish_release import (
    APPS, GitHub, PublishError, TAG_RE, atomic_write, formula_text, parse_event,
    peel_tag, publish, release_record, semver_key, update_manifest,
    validate_manifest, verify_record, verify_release,
)


def latest_payload(gh: GitHub, repo: str) -> dict | None:
    """The dispatch is a wake-up signal; GitHub's latest final release is authoritative."""
    try:
        release = gh.json(f"/repos/{repo}/releases/latest")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None  # Repositories without a first release are expected during bootstrap.
        raise
    tag = release.get("tag_name", "")
    if not isinstance(tag, str) or not TAG_RE.fullmatch(tag):
        raise PublishError(f"{repo}: latest release does not have a stable semantic version tag")
    if release.get("draft") or release.get("prerelease") or not release.get("immutable"):
        raise PublishError(f"{repo}: latest release must be final and immutable")
    checksums = [asset for asset in release.get("assets", []) if asset.get("name") == "checksums.txt"]
    if len(checksums) != 1:
        raise PublishError(f"{repo}: latest release must have exactly one checksums.txt")
    source_sha, _ = peel_tag(gh, repo, tag)
    return {
        "source_repository": repo,
        "release_id": str(release.get("id", "")),
        "tag_name": tag,
        "source_commit": source_sha,
        "checksums_asset_id": str(checksums[0].get("id", "")),
    }


def reconcile(gh: GitHub, original: dict, stage: Path) -> tuple[dict, dict]:
    validate_manifest(original)
    manifest = copy.deepcopy(original)
    verified = {}
    for app, repo in sorted(APPS.values()):
        payload = latest_payload(gh, repo)
        if payload is None:
            continue
        history = manifest["apps"].get(app, [])
        candidate = semver_key(payload["tag_name"])
        if history and candidate < semver_key(history[0]["version"]):
            raise PublishError(f"{repo}: latest release would downgrade the committed manifest")
        # Re-verify a same-version release too: changed immutable identity is an error.
        release = verify_release(gh, app, repo, payload, stage / app / "latest")
        manifest, changed = update_manifest(manifest, release)
        if changed:
            verified[app] = release
    return manifest, verified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--event", type=Path)
    args = parser.parse_args()
    if args.event:
        parse_event(args.event)  # Reject unknown event/repository combinations; do not trust hints.
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise PublishError("GH_TOKEN is required")
    original = json.loads(args.manifest.read_text())
    with tempfile.TemporaryDirectory(prefix="packages-proposal-") as temporary:
        stage = Path(temporary)
        gh = GitHub(token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))
        manifest, newest = reconcile(gh, original, stage)
        changed = manifest != original
        if changed:
            retained = []
            for app, history in sorted(manifest["apps"].items()):
                for index, record in enumerate(history):
                    release = newest.get(app) if index == 0 else None
                    if release is None:
                        release = verify_record(gh, app, record, stage / app / str(index))
                    if release_record(release) != record:
                        raise PublishError(f"{app}: proposal identity does not match verified release")
                    retained.append(release)
                    if index == 0:
                        atomic_write(args.output / "Formula" / f"{app}.rb", formula_text(release).encode())
            # Native metadata, contents, architecture, and dependency validation remains mandatory.
            publish(retained, stage / "site")
            atomic_write(args.output / "manifests/releases.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"changed={'true' if changed else 'false'}\n")
    print("release proposal prepared" if changed else "merged release manifest is current")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        raise SystemExit(f"error: {exc}") from exc
