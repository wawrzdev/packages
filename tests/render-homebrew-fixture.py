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
completion_names = {
    "secret": ("secret.bash", "_secret", "secret.fish"),
    "snip": ("snip.bash", "_snip", "snip.fish"),
    "wtf": ("wtf.bash", "wtf.zsh", "wtf.fish"),
}
for app in ("secret", "snip", "wtf"):
    assets = {}
    checksums = {}
    script = f"#!/bin/sh\necho '{app} 1.2.3'\n".encode()
    for os_name, arch in ARCHIVE_PLATFORMS:
        name = f"{app}_1.2.3_{os_name}_{arch}.tar.gz"
        path = root / name
        files = [(app, script, 0o755)] + [(f"completions/{name}", b"complete", 0o644) for name in completion_names[app]]
        with tarfile.open(path, "w:gz") as archive:
            for filename, data, mode in files:
                info = tarfile.TarInfo(filename)
                info.size = len(data)
                info.mode = mode
                info.mtime = 0
                archive.addfile(info, io.BytesIO(data))
        assets[f"archive:{os_name}:{arch}"] = path
        checksums[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    release = VerifiedRelease(app, f"wawrzdev/{app}", "v1.2.3", "1.2.3", 1, "a" * 40,
                              assets, checksums, {}, 1)
    (root / f"{app}.rb").write_text(formula_text(release, root.as_uri()))
