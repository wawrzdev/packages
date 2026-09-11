#!/usr/bin/env python3
"""Verify one source release and render Homebrew/APT/Pacman outputs.

The GitHub event is treated only as a set of identifiers. All authoritative release,
tag, asset-name, and digest data is fetched again from GitHub before output changes.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

APPS = {
    "secret-release-published": ("secret", "wawrzdev/secret"),
    "snip-release-published": ("snip", "wawrzdev/snip"),
    "wtf-release-published": ("wtf", "wawrzdev/wtf"),
}
ARCHIVE_PLATFORMS = (("darwin", "amd64"), ("darwin", "arm64"), ("linux", "amd64"), ("linux", "arm64"))
LINUX_ARCHES = ("amd64", "arm64")
TAG_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
ASSET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}$")


class PublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedRelease:
    app: str
    repo: str
    tag: str
    version: str
    release_id: int
    source_sha: str
    assets: dict[str, Path]
    checksums: dict[str, str]
    asset_records: dict[str, dict]
    checksums_asset_id: int


class GitHub:
    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")

    def _request(self, path: str, accept: str = "application/vnd.github+json") -> bytes:
        req = urllib.request.Request(
            self.api_url + path,
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "wawrzdev-packages-publisher/1",
            },
        )
        opener = urllib.request.build_opener(StripCrossHostAuthRedirect())
        with opener.open(req, timeout=60) as response:
            return response.read()

    def json(self, path: str) -> dict:
        return json.loads(self._request(path))

    def asset(self, repo: str, asset_id: int) -> bytes:
        return self._request(f"/repos/{repo}/releases/assets/{asset_id}", "application/octet-stream")


def require_string(obj: dict, key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise PublishError(f"client_payload.{key} must be a non-empty string")
    return value


def parse_event(path: Path) -> tuple[str, str, dict]:
    event = json.loads(path.read_text())
    event_type = event.get("action") or os.environ.get("GITHUB_EVENT_ACTION", "")
    if event_type not in APPS:
        raise PublishError(f"unsupported repository_dispatch event: {event_type!r}")
    app, expected_repo = APPS[event_type]
    payload = event.get("client_payload")
    if not isinstance(payload, dict):
        raise PublishError("client_payload must be an object")
    if require_string(payload, "source_repository") != expected_repo:
        raise PublishError(f"event {event_type} only accepts {expected_repo}")
    return app, expected_repo, payload


class StripCrossHostAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


def peel_tag(gh: GitHub, repo: str, tag: str) -> tuple[str, str]:
    ref = gh.json(f"/repos/{repo}/git/ref/tags/{tag}")
    obj = ref.get("object", {})
    ref_sha = str(obj.get("sha", ""))
    for _ in range(2):
        if obj.get("type") == "commit" and re.fullmatch(r"[0-9a-f]{40}", str(obj.get("sha", ""))):
            return obj["sha"], ref_sha
        if obj.get("type") != "tag" or not re.fullmatch(r"[0-9a-f]{40}", str(obj.get("sha", ""))):
            break
        obj = gh.json(f"/repos/{repo}/git/tags/{obj['sha']}").get("object", {})
    raise PublishError("tag does not resolve to a commit")


def parse_checksums(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PublishError("checksums.txt is not UTF-8") from exc
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]{0,199})", line)
        if not match or match.group(2) in result:
            raise PublishError("malformed or duplicate checksums.txt entry")
        result[match.group(2)] = match.group(1).lower()
    if not result:
        raise PublishError("checksums.txt is empty")
    return result


def expected_assets(app: str, version: str, names: list[str]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for os_name, arch in ARCHIVE_PLATFORMS:
        name = f"{app}_{version}_{os_name}_{arch}.tar.gz"
        if name not in names:
            raise PublishError(f"missing required archive: {name}")
        expected[f"archive:{os_name}:{arch}"] = name
    for arch in LINUX_ARCHES:
        for kind, suffix in (("deb", ".deb"), ("pacman", ".pkg.tar.zst")):
            name = f"{app}_{version}_linux_{arch}{suffix}"
            if name not in names:
                raise PublishError(f"missing required {kind} package: {name}")
            expected[f"{kind}:{arch}"] = name
    return expected


def safe_archive_members(path: Path) -> set[str]:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or member.issym() or member.islnk():
                raise PublishError(f"unsafe archive member in {path.name}: {member.name}")
        return {m.name.removeprefix("./") for m in members if m.isfile()}


def validate_archive_contents(app: str, path: Path) -> None:
    members = safe_archive_members(path)
    if app not in members:
        raise PublishError(f"{path.name} does not contain the {app} binary at archive root")
    if not any(n.startswith("completions/") for n in members):
        raise PublishError(f"{path.name} has no completions directory")


def verify_release(gh: GitHub, app: str, repo: str, payload: dict, stage: Path) -> VerifiedRelease:
    release_id_text = require_string(payload, "release_id")
    if not release_id_text.isdigit():
        raise PublishError("release_id must be decimal")
    release_id = int(release_id_text)
    tag = require_string(payload, "tag_name")
    if not TAG_RE.fullmatch(tag):
        raise PublishError("tag_name must be a semantic version tag")
    version = tag.removeprefix("v")
    source_sha = require_string(payload, "source_commit")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise PublishError("source_commit must be a full lowercase SHA")

    release = gh.json(f"/repos/{repo}/releases/{release_id}")
    if release.get("tag_name") != tag or release.get("draft") or release.get("prerelease") or not release.get("immutable"):
        raise PublishError("release ID is not the requested final release")
    commit_sha, tag_object_sha = peel_tag(gh, repo, tag)
    if source_sha not in (commit_sha, tag_object_sha):
        raise PublishError("release tag does not resolve to source_commit")
    target = release.get("target_commitish")
    if re.fullmatch(r"[0-9a-f]{40}", str(target or "")) and target != commit_sha:
        raise PublishError("release target_commitish conflicts with source_commit")

    api_assets = release.get("assets")
    if not isinstance(api_assets, list):
        raise PublishError("release assets are missing")
    by_name: dict[str, dict] = {}
    by_id: dict[int, dict] = {}
    for asset in api_assets:
        name = asset.get("name")
        asset_id = asset.get("id")
        digest = asset.get("digest")
        if (not isinstance(name, str) or not ASSET_RE.fullmatch(name) or not isinstance(asset_id, int)
                or asset.get("state") != "uploaded" or not isinstance(asset.get("size"), int) or asset["size"] <= 0
                or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
            raise PublishError("release contains an invalid asset name or ID")
        if name in by_name or asset_id in by_id:
            raise PublishError("release contains duplicate asset names or IDs")
        by_name[name] = asset
        by_id[asset_id] = asset

    checksum_id_text = require_string(payload, "checksums_asset_id")
    if not checksum_id_text.isdigit() or int(checksum_id_text) not in by_id:
        raise PublishError("checksums_asset_id is not part of the release")
    checksum_asset = by_id[int(checksum_id_text)]
    if checksum_asset["name"] != "checksums.txt":
        raise PublishError("checksums_asset_id does not identify checksums.txt")
    checksum_bytes = gh.asset(repo, checksum_asset["id"])
    if len(checksum_bytes) != checksum_asset["size"]:
        raise PublishError("checksums.txt size does not match GitHub metadata")
    checksum_digest = hashlib.sha256(checksum_bytes).hexdigest()
    api_digest = checksum_asset.get("digest", "")
    payload_digest = payload.get("checksums_digest", "")
    for label, digest in (("API", api_digest), ("payload", payload_digest)):
        if digest and digest != f"sha256:{checksum_digest}":
            raise PublishError(f"checksums.txt {label} digest mismatch")
    checksums = parse_checksums(checksum_bytes)
    required = expected_assets(app, version, list(by_name))
    if set(by_name) != {"checksums.txt", *required.values()}:
        raise PublishError("release contains unexpected assets")
    if set(checksums) != set(required.values()):
        raise PublishError("checksums.txt contains missing or unexpected entries")
    downloaded: dict[str, Path] = {}
    stage.mkdir(parents=True, exist_ok=True)
    for logical, name in required.items():
        if name not in checksums:
            raise PublishError(f"checksums.txt omits {name}")
        asset = by_name[name]
        data = gh.asset(repo, asset["id"])
        if len(data) != asset["size"]:
            raise PublishError(f"asset size mismatch for {name}")
        digest = hashlib.sha256(data).hexdigest()
        if digest != checksums[name]:
            raise PublishError(f"checksum mismatch for {name}")
        if asset["digest"] != f"sha256:{digest}":
            raise PublishError(f"GitHub asset digest mismatch for {name}")
        output = stage / name
        output.write_bytes(data)
        downloaded[logical] = output
    for os_name, arch in ARCHIVE_PLATFORMS:
        validate_archive_contents(app, downloaded[f"archive:{os_name}:{arch}"])
    records = {logical: {"id": by_name[name]["id"], "name": name, "digest": by_name[name]["digest"]} for logical, name in required.items()}
    return VerifiedRelease(app, repo, tag, version, release_id, commit_sha, downloaded, checksums, records, checksum_asset["id"])


def semver_key(version: str) -> tuple[int, int, int, str]:
    match = TAG_RE.fullmatch("v" + version.removeprefix("v"))
    if not match:
        raise PublishError(f"invalid stored version: {version}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), ""


def release_record(release: VerifiedRelease) -> dict:
    return {
        "repository": release.repo, "tag": release.tag, "version": release.version,
        "release_id": release.release_id, "source_sha": release.source_sha,
        "checksums_asset_id": release.checksums_asset_id,
        "assets": release.asset_records,
    }


def update_manifest(manifest: dict, release: VerifiedRelease) -> tuple[dict, bool]:
    apps = manifest.setdefault("apps", {})
    history = apps.setdefault(release.app, [])
    current = release_record(release)
    if history:
        newest = history[0]
        if newest == current:
            return manifest, False
        if semver_key(release.version) <= semver_key(str(newest.get("version", ""))):
            raise PublishError(f"downgrade or conflicting release: {release.version} <= {newest.get('version')}")
    apps[release.app] = [current, *history][:2]
    return manifest, True


def validate_manifest(manifest: dict) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or not isinstance(manifest.get("apps"), dict):
        raise PublishError("release manifest must use schema 1")
    allowed_apps = {value[0] for value in APPS.values()}
    if not set(manifest["apps"]).issubset(allowed_apps):
        raise PublishError("release manifest contains an unknown application")
    for app, history in manifest["apps"].items():
        if not isinstance(history, list) or len(history) > 2:
            raise PublishError(f"release manifest history for {app} must contain at most two releases")
        versions = [semver_key(str(record.get("version", ""))) for record in history if isinstance(record, dict)]
        if len(versions) != len(history) or versions != sorted(versions, reverse=True) or len(set(versions)) != len(versions):
            raise PublishError(f"release manifest history for {app} is not strictly newest-first")


def verify_record(gh: GitHub, app: str, record: dict, stage: Path) -> VerifiedRelease:
    if record.get("repository") != f"wawrzdev/{app}" or not isinstance(record.get("assets"), dict):
        raise PublishError(f"invalid committed manifest record for {app}")
    payload = {
        "release_id": str(record.get("release_id", "")), "tag_name": record.get("tag", ""),
        "source_commit": record.get("source_sha", ""), "checksums_asset_id": str(record.get("checksums_asset_id", "")),
        "source_repository": record["repository"],
    }
    verified = verify_release(gh, app, record["repository"], payload, stage)
    if release_record(verified) != record:
        raise PublishError(f"immutable release metadata changed for {app} {record.get('version')}")
    return verified


def formula_text(release: VerifiedRelease) -> str:
    app = release.app
    descriptions = {
        "secret": "Generate and store private machine-local credentials",
        "snip": "Manage GitHub gists and GitLab snippets as local Git clones",
        "wtf": "Discover commands and compose local documentation",
    }
    checks = {(os_name, arch): release.checksums[release.assets[f"archive:{os_name}:{arch}"].name] for os_name, arch in ARCHIVE_PLATFORMS}
    completion_lines = {
        "secret": '    bash_completion.install "completions/secret.bash" => "secret"\n    zsh_completion.install "completions/_secret"\n    fish_completion.install "completions/secret.fish"',
        "snip": '    bash_completion.install "completions/snip.bash" => "snip"\n    zsh_completion.install "completions/_snip"\n    fish_completion.install "completions/snip.fish"',
        "wtf": '    bash_completion.install "completions/wtf.bash" => "wtf"\n    zsh_completion.install "completions/wtf.zsh" => "_wtf"\n    fish_completion.install "completions/wtf.fish"',
    }[app]
    dependencies = {
        "secret": "",
        "snip": '\n  depends_on "git"\n  depends_on "fzf"\n  depends_on "gh"\n',
        "wtf": '\n  depends_on "fzf"\n',
    }[app]
    class_name = "".join(part.capitalize() for part in app.split("-"))
    return f'''class {class_name} < Formula
  desc "{descriptions[app]}"
  homepage "https://github.com/{release.repo}"
  version "{release.version}"
  license "MIT"
{dependencies}

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/{release.repo}/releases/download/{release.tag}/{app}_{release.version}_darwin_arm64.tar.gz"
      sha256 "{checks[("darwin", "arm64")]}"
    else
      url "https://github.com/{release.repo}/releases/download/{release.tag}/{app}_{release.version}_darwin_amd64.tar.gz"
      sha256 "{checks[("darwin", "amd64")]}"
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/{release.repo}/releases/download/{release.tag}/{app}_{release.version}_linux_arm64.tar.gz"
      sha256 "{checks[("linux", "arm64")]}"
    else
      url "https://github.com/{release.repo}/releases/download/{release.tag}/{app}_{release.version}_linux_amd64.tar.gz"
      sha256 "{checks[("linux", "amd64")]}"
    end
  end

  def install
    bin.install "{app}"
{completion_lines}
  end

  test do
    assert_match version.to_s, shell_output("#{{bin}}/{app} --version")
  end
end
'''


def read_ar_member(path: Path, wanted: str) -> bytes:
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise PublishError(f"{path.name} is not a Debian ar archive")
    pos = 8
    while pos + 60 <= len(data):
        header = data[pos : pos + 60]
        if header[58:60] != b"`\n":
            raise PublishError(f"invalid ar header in {path.name}")
        name = header[:16].decode("ascii").strip().rstrip("/")
        try:
            size = int(header[48:58].decode("ascii").strip())
        except ValueError as exc:
            raise PublishError("invalid ar member size") from exc
        pos += 60
        member = data[pos : pos + size]
        if len(member) != size:
            raise PublishError("truncated ar member")
        if name.startswith(wanted):
            return member
        pos += size + (size % 2)
    raise PublishError(f"{path.name} has no {wanted} member")


def deb_control(path: Path) -> dict[str, str]:
    compressed = read_ar_member(path, "control.tar")
    data_archive = read_ar_member(path, "data.tar")
    validate_tar_bytes(data_archive, "Debian data archive")
    compressed = decompressed_tar_bytes(compressed, "Debian control archive")
    try:
        with tarfile.open(fileobj=io.BytesIO(compressed), mode="r:*") as archive:
            members = archive.getmembers()
            for member in members:
                pure = PurePosixPath(member.name)
                if pure.is_absolute() or ".." in pure.parts or member.issym() or member.islnk():
                    raise PublishError("unsafe Debian control archive")
            member = next((m for m in members if m.name.removeprefix("./") == "control" and m.isfile()), None)
            if member is None or member.size > 64 * 1024:
                raise PublishError("Debian control file is missing or too large")
            raw = archive.extractfile(member).read().decode("utf-8")
    except (tarfile.TarError, UnicodeDecodeError) as exc:
        raise PublishError("invalid Debian control archive") from exc
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if line.startswith((" ", "\t")):
            continue
        if ": " in line:
            key, value = line.split(": ", 1)
            fields[key] = value
    for required in ("Package", "Version", "Architecture", "Description"):
        if required not in fields:
            raise PublishError(f"Debian control omits {required}")
    return fields


def decompressed_tar_bytes(data: bytes, label: str) -> bytes:
    if data[:4] != b"\x28\xb5\x2f\xfd":
        return data
    result = subprocess.run(["zstd", "-q", "-d", "-c"], input=data, capture_output=True, check=False)
    if result.returncode:
        raise PublishError(f"zstd could not decompress {label}")
    return result.stdout


def validate_tar_bytes(data: bytes, label: str) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(decompressed_tar_bytes(data, label)), mode="r:*") as archive:
            for member in archive.getmembers():
                pure = PurePosixPath(member.name)
                if pure.is_absolute() or ".." in pure.parts or member.issym() or member.islnk():
                    raise PublishError(f"unsafe member in {label}: {member.name}")
    except tarfile.TarError as exc:
        raise PublishError(f"invalid {label}") from exc


def pkginfo(path: Path) -> dict[str, list[str]]:
    temp: tempfile.TemporaryDirectory[str] | None = None
    source = path
    if path.read_bytes()[:4] == b"\x28\xb5\x2f\xfd":
        temp = tempfile.TemporaryDirectory()
        source = Path(temp.name) / "package.tar"
        with source.open("wb") as stream:
            result = subprocess.run(["zstd", "-q", "-d", "-c", str(path)], stdout=stream, check=False)
        if result.returncode:
            raise PublishError("zstd could not decompress Arch package")
    try:
        members = safe_archive_members_plain(source)
        member = next((m for m in members if m.name.removeprefix("./") == ".PKGINFO"), None)
        if member is None or member.size > 64 * 1024:
            raise PublishError("Arch package has no valid .PKGINFO")
        with tarfile.open(source, "r:") as archive:
            raw = archive.extractfile(member).read().decode("utf-8")
    finally:
        if temp:
            temp.cleanup()
    fields: dict[str, list[str]] = {}
    for line in raw.splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            fields.setdefault(key, []).append(value)
    for required in ("pkgname", "pkgver", "arch", "pkgdesc"):
        if required not in fields:
            raise PublishError(f"Arch .PKGINFO omits {required}")
    return fields


def safe_archive_members_plain(path: Path) -> list[tarfile.TarInfo]:
    try:
        with tarfile.open(path, "r:") as archive:
            members = archive.getmembers()
            for member in members:
                pure = PurePosixPath(member.name)
                if pure.is_absolute() or ".." in pure.parts or member.issym() or member.islnk():
                    raise PublishError(f"unsafe package member: {member.name}")
            return members
    except tarfile.TarError as exc:
        raise PublishError(f"invalid tar archive: {path.name}") from exc


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data)
    temp.replace(path)


def render_apt(site: Path) -> None:
    pool = site / "apt" / "pool" / "main"
    records: dict[str, list[str]] = {"amd64": [], "arm64": []}
    for package in sorted(pool.glob("*/*/*.deb")):
        fields = deb_control(package)
        arch = fields["Architecture"]
        if arch not in records:
            continue
        relative = package.relative_to(site / "apt").as_posix()
        size = package.stat().st_size
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        ordered = [f"{key}: {fields[key]}" for key in ("Package", "Version", "Architecture")]
        for key in ("Maintainer", "Depends", "Homepage", "Description"):
            if key in fields:
                ordered.append(f"{key}: {fields[key]}")
        ordered.extend((f"Filename: {relative}", f"Size: {size}", f"SHA256: {digest}"))
        records[arch].append("\n".join(ordered) + "\n")
    for arch, items in records.items():
        directory = site / "apt" / "dists" / "stable" / "main" / f"binary-{arch}"
        packages = ("\n".join(sorted(items))).encode()
        atomic_write(directory / "Packages", packages)
        stream = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as gz:
            gz.write(packages)
        atomic_write(directory / "Packages.gz", stream.getvalue())
        for path in (directory / "Packages", directory / "Packages.gz"):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            atomic_write(directory / "by-hash" / "SHA256" / digest, path.read_bytes())
    release_lines = [
        "Origin: wawrzdev", "Label: wawrzdev packages", "Suite: stable", "Codename: stable",
        "Architectures: amd64 arm64", "Components: main", "Acquire-By-Hash: yes", "Description: wawrzdev command-line packages",
        "Date: Thu, 01 Jan 1970 00:00:00 +0000", "SHA256:",
    ]
    dist = site / "apt" / "dists" / "stable"
    for path in sorted(path for path in dist.glob("main/binary-*/*") if path.is_file()):
        data = path.read_bytes()
        release_lines.append(f" {hashlib.sha256(data).hexdigest()} {len(data):16d} {path.relative_to(dist).as_posix()}")
    atomic_write(dist / "Release", ("\n".join(release_lines) + "\n").encode())


def pacman_desc(fields: dict[str, list[str]], filename: str, size: int, digest: str, signature: str = "") -> bytes:
    mapping = (("FILENAME", [filename]), ("NAME", fields["pkgname"]), ("VERSION", fields["pkgver"]),
               ("DESC", fields["pkgdesc"]), ("CSIZE", [str(size)]), ("SHA256SUM", [digest]),
               ("PGPSIG", [signature] if signature else []), ("URL", fields.get("url", [])),
               ("BUILDDATE", fields.get("builddate", [])), ("PACKAGER", fields.get("packager", [])),
               ("ISIZE", fields.get("size", [])), ("ARCH", fields["arch"]),
               ("LICENSE", fields.get("license", [])), ("DEPENDS", fields.get("depend", [])))
    parts = []
    for key, values in mapping:
        if values:
            parts.append(f"%{key}%\n" + "\n".join(values) + "\n")
    return ("\n".join(parts) + "\n").encode()


def deterministic_tar_gz(entries: list[tuple[str, bytes]]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for name, data in sorted(entries):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            archive.addfile(info, io.BytesIO(data))
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as gz:
        gz.write(raw.getvalue())
    return output.getvalue()


def render_pacman(site: Path) -> None:
    for repo_arch, package_arch in (("x86_64", "x86_64"), ("aarch64", "aarch64")):
        directory = site / "pacman" / repo_arch
        entries: list[tuple[str, bytes]] = []
        for package in sorted(directory.glob("*.pkg.tar.zst")):
            fields = pkginfo(package)
            if fields["arch"] != [package_arch]:
                raise PublishError(f"{package.name} has unexpected Arch architecture")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            stem = f"{fields['pkgname'][0]}-{fields['pkgver'][0]}"
            entries.append((f"{stem}/desc", pacman_desc(fields, package.name, package.stat().st_size, digest)))
        db = deterministic_tar_gz(entries)
        atomic_write(directory / "wawrzdev.db.tar.gz", db)
        atomic_write(directory / "wawrzdev.files.tar.gz", db)


def publish(releases: list[VerifiedRelease], output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for release in releases:
        for arch in LINUX_ARCHES:
            deb = release.assets[f"deb:{arch}"]
            deb_fields = deb_control(deb)
            if deb_fields["Package"] != release.app or deb_fields["Version"].lstrip("v") != release.version or deb_fields["Architecture"] != arch:
                raise PublishError(f"unexpected Debian metadata in {deb.name}")
            target = output / "apt" / "pool" / "main" / release.app[0] / release.app / deb.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(deb, target)
            package = release.assets[f"pacman:{arch}"]
            fields = pkginfo(package)
            expected_arch = "x86_64" if arch == "amd64" else "aarch64"
            if (fields["pkgname"] != [release.app]
                    or fields["pkgver"][0].lstrip("v") not in (release.version, release.version + "-1")
                    or fields["arch"] != [expected_arch]):
                raise PublishError(f"unexpected Arch metadata in {package.name}")
            destination = output / "pacman" / expected_arch / package.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package, destination)
    render_apt(output)
    render_pacman(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formula-output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise PublishError("GH_TOKEN is required")
    with tempfile.TemporaryDirectory(prefix="packages-release-") as temp:
        manifest = json.loads(args.manifest.read_text()) if args.manifest.exists() else {"schema": 1, "apps": {}}
        validate_manifest(manifest)
        gh = GitHub(token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))
        release = None
        app = ""
        changed = True
        if args.event:
            app, repo, payload = parse_event(args.event)
            release = verify_release(gh, app, repo, payload, Path(temp) / "new")
            manifest, changed = update_manifest(manifest, release)
        if changed:
            retained = []
            for retained_app, records in sorted(manifest["apps"].items()):
                for index, record in enumerate(records):
                    if release is not None and retained_app == app and index == 0:
                        retained.append(release)
                    else:
                        retained.append(verify_record(gh, retained_app, record, Path(temp) / retained_app / str(index)))
            publish(retained, args.output)
            if release is not None:
                args.formula_output.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(args.formula_output, formula_text(release).encode())
            atomic_write(args.manifest_output, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"changed={'true' if changed else 'false'}\napp={app}\nversion={release.version if release else ''}\n")
    print("repositories rebuilt" if not args.event else f"{'published' if changed else 'already published'} {app} {release.version}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        raise SystemExit(f"error: {exc}") from exc
