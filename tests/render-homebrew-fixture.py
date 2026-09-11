#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from publish_release import ARCHIVE_PLATFORMS, VerifiedRelease, formula_text

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
assets = {}
checksums = {}
script = b"#!/bin/sh\necho 'secret 1.2.3'\n"
for os_name, arch in ARCHIVE_PLATFORMS:
    name = f"secret_1.2.3_{os_name}_{arch}.tar.gz"
    path = root / name
    with tarfile.open(path, "w:gz") as archive:
        for filename, data, mode in (("secret", script, 0o755), ("completions/secret.bash", b"complete", 0o644),
                                     ("completions/_secret", b"compdef", 0o644), ("completions/secret.fish", b"complete", 0o644)):
            info = tarfile.TarInfo(filename)
            info.size = len(data)
            info.mode = mode
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
    assets[f"archive:{os_name}:{arch}"] = path
    checksums[name] = hashlib.sha256(path.read_bytes()).hexdigest()
release = VerifiedRelease("secret", "wawrzdev/secret", "v1.2.3", "1.2.3", 1, "a" * 40,
                          assets, checksums, {}, 1)
(root / "secret.rb").write_text(formula_text(release, root.as_uri()))
