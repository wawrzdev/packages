#!/usr/bin/env python3
"""Rebuild deterministic Pacman databases with embedded package signatures."""

from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

from publish_release import PublishError, atomic_write, deterministic_tar_gz, pacman_desc, pkginfo


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site", type=Path)
    args = parser.parse_args()
    for repo_arch, expected_arch in (("x86_64", "x86_64"), ("aarch64", "aarch64")):
        directory = args.site / "pacman" / repo_arch
        entries = []
        for package in sorted(directory.glob("*.pkg.tar.zst")):
            fields = pkginfo(package)
            if fields["arch"] != [expected_arch]:
                raise PublishError(f"{package.name} has unexpected architecture")
            signature_path = package.with_name(package.name + ".sig")
            if not signature_path.is_file():
                raise PublishError(f"missing signature for {package.name}")
            signature = base64.b64encode(signature_path.read_bytes()).decode("ascii")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            stem = f"{fields['pkgname'][0]}-{fields['pkgver'][0]}"
            entries.append((f"{stem}/desc", pacman_desc(fields, package.name, package.stat().st_size, digest, signature)))
        database = deterministic_tar_gz(entries)
        atomic_write(directory / "wawrzdev.db.tar.gz", database)
        atomic_write(directory / "wawrzdev.files.tar.gz", database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
