#!/usr/bin/env python3
"""Apply a final size and file-type allowlist to the Pages tree."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

MAX_SITE_SIZE = 900 * 1024 * 1024
ALLOWED = [
    re.compile(r"apt/pool/main/[a-z]/(?:secret|snip|wtf)/[A-Za-z0-9._+-]+\.deb"),
    re.compile(r"apt/dists/stable/main/binary-(?:amd64|arm64)/(?:Packages(?:\.gz)?|by-hash/SHA256/[0-9a-f]{64})"),
    re.compile(r"apt/dists/stable/(?:Release|InRelease|Release\.gpg)"),
    re.compile(r"pacman/(?:x86_64|aarch64)/(?:[A-Za-z0-9._+-]+\.pkg\.tar\.zst(?:\.sig)?|wawrzdev\.(?:db|files)(?:\.tar\.gz)?(?:\.sig)?)"),
    re.compile(r"keys/wawrzdev-packages\.(?:gpg|asc)"),
]


def validate(root: Path) -> None:
    total = 0
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError(f"symbolic link is forbidden: {relative}")
        if path.is_dir():
            continue
        if not path.is_file() or path.stat().st_nlink != 1 or not any(pattern.fullmatch(relative) for pattern in ALLOWED):
            raise ValueError(f"unexpected Pages file: {relative}")
        total += path.stat().st_size
        if total > MAX_SITE_SIZE:
            raise ValueError("Pages tree exceeds 900 MiB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site", type=Path)
    args = parser.parse_args()
    validate(args.site)
    print(f"validated Pages tree: {sum(p.stat().st_size for p in args.site.rglob('*') if p.is_file())} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
