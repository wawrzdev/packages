from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("publisher", Path(__file__).parents[1] / "scripts" / "publish_release.py")
publisher = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = publisher
SPEC.loader.exec_module(publisher)


def tar_bytes(files: dict[str, bytes], mode: str = "w:gz") -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode=mode) as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def ar_member(name: str, data: bytes) -> bytes:
    header = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n".encode()
    return header + data + (b"\n" if len(data) % 2 else b"")


def deb_bytes(app: str, version: str, arch: str) -> bytes:
    control = f"Package: {app}\nVersion: {version}\nArchitecture: {arch}\nMaintainer: Test <test@example.com>\nDescription: test package\n".encode()
    return b"!<arch>\n" + ar_member("debian-binary", b"2.0\n") + ar_member("control.tar.gz", tar_bytes({"./control": control})) + ar_member("data.tar.gz", tar_bytes({"./usr/bin/" + app: b"bin"}))


def pkg_bytes(app: str, version: str, arch: str) -> bytes:
    info = f"pkgname = {app}\npkgver = {version}-1\narch = {arch}\npkgdesc = test package\nlicense = MIT\n".encode()
    return tar_bytes({".PKGINFO": info, "usr/bin/" + app: b"bin"}, "w:")


def release_fixture(root: Path, app: str = "secret", version: str = "1.2.3"):
    assets = {}
    checksums = {}
    for os_name, arch in publisher.ARCHIVE_PLATFORMS:
        name = f"{app}_{version}_{os_name}_{arch}.tar.gz"
        path = root / name
        path.write_bytes(tar_bytes({app: b"binary", f"completions/{app}.bash": b"complete"}))
        assets[f"archive:{os_name}:{arch}"] = path
        checksums[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for arch in publisher.LINUX_ARCHES:
        deb = root / f"{app}_{version}_linux_{arch}.deb"
        deb.write_bytes(deb_bytes(app, version, arch))
        assets[f"deb:{arch}"] = deb
        checksums[deb.name] = hashlib.sha256(deb.read_bytes()).hexdigest()
        package = root / f"{app}_{version}_linux_{arch}.pkg.tar.zst"
        package.write_bytes(pkg_bytes(app, version, "x86_64" if arch == "amd64" else "aarch64"))
        assets[f"pacman:{arch}"] = package
        checksums[package.name] = hashlib.sha256(package.read_bytes()).hexdigest()
    records = {key: {"id": index, "name": path.name, "digest": "sha256:" + checksums[path.name]} for index, (key, path) in enumerate(sorted(assets.items()), 1)}
    return publisher.VerifiedRelease(app, f"wawrzdev/{app}", f"v{version}", version, 42, "a" * 40, assets, checksums, records, 99)


class PublisherTests(unittest.TestCase):
    def test_verify_release_uses_authoritative_ids_digests_and_exact_asset_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = release_fixture(root)
            blobs = {index: path.read_bytes() for index, path in enumerate(fixture.assets.values(), 1)}
            checksum_text = "".join(f"{fixture.checksums[path.name]}  {path.name}\n" for path in fixture.assets.values()).encode()
            blobs[99] = checksum_text
            assets = []
            for asset_id, data in blobs.items():
                name = "checksums.txt" if asset_id == 99 else list(fixture.assets.values())[asset_id - 1].name
                assets.append({"id": asset_id, "name": name, "state": "uploaded", "size": len(data),
                               "digest": "sha256:" + hashlib.sha256(data).hexdigest()})

            class FakeGitHub:
                def json(self, path):
                    if "/releases/" in path:
                        return {"tag_name": "v1.2.3", "draft": False, "prerelease": False, "immutable": True,
                                "target_commitish": "a" * 40, "assets": assets}
                    if "/git/ref/tags/" in path:
                        return {"object": {"type": "commit", "sha": "a" * 40}}
                    raise AssertionError(path)

                def asset(self, repo, asset_id):
                    self.assert_repo = repo
                    return blobs[asset_id]

            payload = {"release_id": "42", "tag_name": "v1.2.3", "source_commit": "a" * 40,
                       "checksums_asset_id": "99", "source_repository": "wawrzdev/secret"}
            verified = publisher.verify_release(FakeGitHub(), "secret", "wawrzdev/secret", payload, root / "stage")
            self.assertEqual("1.2.3", verified.version)
            assets.append({"id": 100, "name": "surprise", "state": "uploaded", "size": 1, "digest": "sha256:" + "0" * 64})
            with self.assertRaisesRegex(publisher.PublishError, "unexpected assets"):
                publisher.verify_release(FakeGitHub(), "secret", "wawrzdev/secret", payload, root / "other")

    def test_event_allowlist_rejects_spoofed_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({"action": "secret-release-published", "client_payload": {"source_repository": "attacker/secret"}}))
            with self.assertRaisesRegex(publisher.PublishError, "only accepts"):
                publisher.parse_event(event)

    def test_checksums_reject_paths_and_duplicates(self):
        digest = "a" * 64
        with self.assertRaises(publisher.PublishError):
            publisher.parse_checksums(f"{digest}  ../secret.tar.gz\n".encode())
        with self.assertRaises(publisher.PublishError):
            publisher.parse_checksums(f"{digest}  file.tar.gz\n{digest}  file.tar.gz\n".encode())

    def test_archive_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.tar.gz"
            path.write_bytes(tar_bytes({"../secret": b"bad", "completions/secret.bash": b"x"}))
            with self.assertRaisesRegex(publisher.PublishError, "unsafe archive"):
                publisher.validate_archive_contents("secret", path)

    def test_debian_package_rejects_data_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.deb"
            control = b"Package: secret\nVersion: 1.2.3\nArchitecture: amd64\nDescription: test\n"
            path.write_bytes(b"!<arch>\n" + ar_member("debian-binary", b"2.0\n")
                             + ar_member("control.tar.gz", tar_bytes({"control": control}))
                             + ar_member("data.tar.gz", tar_bytes({"../secret": b"bad"})))
            with self.assertRaisesRegex(publisher.PublishError, "unsafe member"):
                publisher.deb_control(path)

    def test_publish_generates_formula_indexes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "fixture"
            fixture.mkdir()
            release = release_fixture(fixture)
            output = root / "output"
            formula = root / "Formula" / "secret.rb"
            publisher.publish([release], output)
            formula.parent.mkdir(parents=True)
            formula.write_text(publisher.formula_text(release))
            text = formula.read_text()
            self.assertIn('class Secret < Formula', text)
            self.assertIn('bash_completion.install "completions/secret.bash" => "secret"', text)
            packages = (output / "apt/dists/stable/main/binary-amd64/Packages").read_text()
            self.assertIn("Package: secret", packages)
            self.assertIn("SHA256:", (output / "apt/dists/stable/Release").read_text())
            with tarfile.open(output / "pacman/x86_64/wawrzdev.db.tar.gz", "r:gz") as database:
                self.assertIn("secret-1.2.3-1/desc", database.getnames())
            manifest, changed = publisher.update_manifest({"schema": 1, "apps": {}}, release)
            self.assertTrue(changed)
            same, changed = publisher.update_manifest(manifest, release)
            self.assertFalse(changed)
            self.assertEqual(manifest, same)

    def test_same_version_conflict_and_downgrade_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "fixture"
            fixture.mkdir()
            release = release_fixture(fixture)
            manifest, _ = publisher.update_manifest({"schema": 1, "apps": {}}, release)
            conflict = publisher.VerifiedRelease(**{**release.__dict__, "release_id": 43})
            with self.assertRaisesRegex(publisher.PublishError, "conflicting"):
                publisher.update_manifest(manifest, conflict)

    def test_manifest_rejects_unknown_app_and_excess_history(self):
        with self.assertRaisesRegex(publisher.PublishError, "unknown application"):
            publisher.validate_manifest({"schema": 1, "apps": {"evil": []}})
        record = {"version": "1.2.3"}
        with self.assertRaisesRegex(publisher.PublishError, "at most two"):
            publisher.validate_manifest({"schema": 1, "apps": {"secret": [record, record, record]}})

    def test_all_formulae_install_dependencies_and_completions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formulae = {}
            for app in ("secret", "snip", "wtf"):
                app_root = root / app
                app_root.mkdir()
                text = publisher.formula_text(release_fixture(app_root, app))
                formulae[app] = text
                self.assertIn(f'bin.install "{app}"', text)
                self.assertIn(f'shell_output("#{{bin}}/{app} --version")', text)
            self.assertIn('depends_on "gh"', formulae["snip"])
            self.assertIn('depends_on "fzf"', formulae["snip"])
            self.assertIn('depends_on "fzf"', formulae["wtf"])
            self.assertNotIn("depends_on", formulae["secret"])


if __name__ == "__main__":
    unittest.main()
