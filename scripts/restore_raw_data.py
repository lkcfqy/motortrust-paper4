#!/usr/bin/env python3
"""Verify and restore MotorTrust raw-data Release parts (Python 3.8+, standard library).

Usage: python scripts/restore_raw_data.py --parts-dir /path/to/downloaded/assets
The assets directory must contain raw-data-manifest.json and every named part.
Dataset attribution and original license files are restored without changing their bytes.
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import stat
import sys
import tarfile
import tempfile
import unicodedata
import zlib
from pathlib import Path

CHUNK_SIZE = 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
DEVICE_PATTERN = re.compile(r"(?:con|prn|aux|nul|com[1-9\u00b9\u00b2\u00b3]|lpt[1-9\u00b9\u00b2\u00b3])\Z", re.IGNORECASE)
FORBIDDEN_CHARACTERS = set('<>:"\\|?*')


class RestoreError(Exception):
    """A verification or destination-safety failure; no existing file is replaced."""


def canonical(value):
    return unicodedata.normalize("NFKC", value).casefold()


def portable_component(value):
    if not isinstance(value, str) or not value or value in (".", ".."):
        raise RestoreError("Empty or relative path component is forbidden")
    if "/" in value or any(char in FORBIDDEN_CHARACTERS for char in value):
        raise RestoreError(f"Nonportable path component: {value!r}")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise RestoreError(f"Control character in path component: {value!r}")
    if value.endswith((" ", ".")):
        raise RestoreError(f"Trailing space/dot in path component: {value!r}")
    normalized = canonical(value)
    if normalized in (".", "..", ".git"):
        raise RestoreError(f"Reserved path component: {value!r}")
    if any(char in FORBIDDEN_CHARACTERS or char == "/" for char in normalized):
        raise RestoreError(f"Nonportable normalized component: {value!r}")
    if normalized.endswith((" ", ".")):
        raise RestoreError(f"Trailing normalized space/dot: {value!r}")
    if DEVICE_PATTERN.fullmatch(normalized.split(".", 1)[0]):
        raise RestoreError(f"Windows device name is forbidden: {value!r}")
    try:
        if len(value.encode("utf-8")) > 255:
            raise RestoreError("Path component exceeds 255 bytes")
    except UnicodeEncodeError as exc:
        raise RestoreError("Invalid Unicode path component") from exc
    return value


def raw_path(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise RestoreError("Invalid raw file path")
    components = value.split("/")
    if len(components) < 3 or components[:2] != ["data", "raw"]:
        raise RestoreError(f"File must be inside data/raw/: {value!r}")
    for component in components:
        portable_component(component)
    return value


def nonnegative_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RestoreError(f"{label} must be a nonnegative integer")
    return value


def expected_hash(value, label):
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise RestoreError(f"{label} must be a lowercase SHA-256 value")
    return value


def reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RestoreError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def open_regular(path):
    """Reject symlinks, devices and pipes before reading a local file."""
    try:
        before = path.lstat()
    except OSError as exc:
        raise RestoreError(f"Cannot read required file: {path}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise RestoreError(f"Expected a regular file, found link or other type: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(path), flags)
    observed = os.fstat(descriptor)
    if not stat.S_ISREG(observed.st_mode) or (before.st_dev, before.st_ino) != (
        observed.st_dev, observed.st_ino
    ):
        os.close(descriptor)
        raise RestoreError(f"File changed while opening: {path}")
    return os.fdopen(descriptor, "rb")


def verify_file(path, entry):
    digest = hashlib.sha256()
    size = 0
    with open_regular(path) as stream:
        before = os.fstat(stream.fileno())
        if before.st_size != entry["size_bytes"]:
            raise RestoreError(f"File size mismatch: {path}")
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RestoreError(f"File changed while checking: {path}")
    if size != entry["size_bytes"] or digest.hexdigest() != entry["sha256"]:
        raise RestoreError(f"File hash mismatch: {path}")


def read_manifest_bytes(path):
    with open_regular(path) as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > MAX_MANIFEST_BYTES:
            raise RestoreError(f"Manifest exceeds the 16 MiB limit: {path}")
        content = stream.read(MAX_MANIFEST_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(content) > MAX_MANIFEST_BYTES:
        raise RestoreError(f"Manifest exceeds the 16 MiB limit: {path}")
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RestoreError(f"Manifest changed while reading: {path}")
    return content


def load_manifest(parts_dir, project=None):
    path = parts_dir / "raw-data-manifest.json"
    content = read_manifest_bytes(path)
    if project is not None:
        known_path = project / "recovery" / "raw-data-manifest.json"
        try:
            known_path.lstat()
        except FileNotFoundError:
            pass
        else:
            known = read_manifest_bytes(known_path)
            if hashlib.sha256(content).digest() != hashlib.sha256(known).digest():
                raise RestoreError("Downloaded manifest differs from the committed project manifest; "
                                   "check the paper and Release version")
    try:
        manifest = json.loads(content, object_pairs_hook=reject_duplicate_json_keys)
    except (ValueError, UnicodeError) as exc:
        raise RestoreError("Invalid raw-data manifest JSON") from exc
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
            or manifest.get("schema_version") != 1):
        raise RestoreError("Unsupported raw-data manifest schema")
    paper = manifest.get("paper")
    if type(paper) is not int or paper not in (1, 2, 3, 4):
        raise RestoreError("Manifest paper must be an integer from 1 to 4")
    archive = manifest.get("archive")
    if not isinstance(archive, dict) or archive.get("format") != "tar.gz":
        raise RestoreError("Manifest archive must have tar.gz format")
    portable_component(archive.get("filename"))
    nonnegative_integer(archive.get("size_bytes"), "archive size_bytes")
    nonnegative_integer(archive.get("unpacked_size_bytes"), "archive unpacked_size_bytes")
    expected_hash(archive.get("sha256"), "archive sha256")
    parts = manifest.get("parts")
    if not isinstance(parts, list) or not parts:
        raise RestoreError("Manifest must list one or more ordered archive parts")
    part_names = set()
    for part in parts:
        if not isinstance(part, dict):
            raise RestoreError("Invalid archive part entry")
        name = portable_component(part.get("filename"))
        key = canonical(name)
        if key in part_names:
            raise RestoreError(f"Duplicate or aliased archive part name: {name}")
        part_names.add(key)
        nonnegative_integer(part.get("size_bytes"), "part size_bytes")
        expected_hash(part.get("sha256"), "part sha256")
    if sum(part["size_bytes"] for part in parts) != archive["size_bytes"]:
        raise RestoreError("Part sizes do not sum to archive size")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise RestoreError("Manifest must list one or more raw files")
    entries = {}
    prefixes = {}
    for entry in files:
        if not isinstance(entry, dict):
            raise RestoreError("Invalid raw file entry")
        name = raw_path(entry.get("path"))
        if name in entries:
            raise RestoreError(f"Duplicate raw file path: {name}")
        nonnegative_integer(entry.get("size_bytes"), "file size_bytes")
        expected_hash(entry.get("sha256"), "file sha256")
        components = name.split("/")
        for count in range(1, len(components) + 1):
            prefix = "/".join(components[:count])
            key = canonical(prefix)
            kind = "file" if count == len(components) else "directory"
            previous = prefixes.get(key)
            if previous is not None and previous != (prefix, kind):
                raise RestoreError(f"Case/Unicode alias or file/directory collision: {name}")
            prefixes[key] = (prefix, kind)
        entries[name] = entry
    if sum(entry["size_bytes"] for entry in files) != archive["unpacked_size_bytes"]:
        raise RestoreError("Raw file sizes do not sum to unpacked archive size")
    return manifest, entries


def concatenate_parts(parts_dir, combined, manifest):
    digest = hashlib.sha256()
    total = 0
    with combined.open("xb") as output:
        for part in manifest["parts"]:
            path = parts_dir / part["filename"]
            part_digest = hashlib.sha256()
            part_size = 0
            with open_regular(path) as source:
                before = os.fstat(source.fileno())
                if before.st_size != part["size_bytes"]:
                    raise RestoreError(f"Archive part size mismatch: {path.name}")
                for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                    part_digest.update(chunk)
                    digest.update(chunk)
                    part_size += len(chunk)
                    total += len(chunk)
                    output.write(chunk)
                after = os.fstat(source.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RestoreError(f"Archive part changed while reading: {path.name}")
            if part_size != part["size_bytes"] or part_digest.hexdigest() != part["sha256"]:
                raise RestoreError(f"Archive part hash mismatch: {path.name}")
    archive = manifest["archive"]
    if total != archive["size_bytes"] or digest.hexdigest() != archive["sha256"]:
        raise RestoreError("Concatenated archive size/hash mismatch")


class BoundedReader:
    """Bound expanded tar bytes, including headers and zero padding."""

    def __init__(self, stream, limit):
        self.stream = stream
        self.remaining = limit

    def read(self, size=-1):
        if size < 0:
            size = self.remaining + 1
        data = self.stream.read(min(size, self.remaining + 1))
        self.remaining -= len(data)
        if self.remaining < 0:
            raise RestoreError("Expanded archive exceeds the declared files and header allowance")
        return data


def stage_archive(combined, staged, manifest, entries):
    seen = set()
    limit = manifest["archive"]["unpacked_size_bytes"] + 16384 * len(entries) + 10240
    with combined.open("rb") as source, gzip.GzipFile(fileobj=source, mode="rb") as compressed:
        bounded = BoundedReader(compressed, limit)
        # Reading through padding also rejects appended archives/entries and verifies gzip CRC.
        with tarfile.open(fileobj=bounded, mode="r|", ignore_zeros=True) as archive:
            for member in archive:
                name = raw_path(member.name)
                if name in seen:
                    raise RestoreError(f"Duplicate archive member: {name}")
                if not member.isreg() or member.linkname or member.sparse is not None:
                    raise RestoreError(f"Only ordinary regular files are allowed: {name}")
                if any(key.startswith("GNU.sparse") for key in member.pax_headers):
                    raise RestoreError(f"Sparse archive members are forbidden: {name}")
                entry = entries.get(name)
                if entry is None:
                    raise RestoreError(f"Unlisted or aliased archive member: {name}")
                if member.size != entry["size_bytes"]:
                    raise RestoreError(f"Archive member size mismatch: {name}")
                target = staged.joinpath(*name.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                content = archive.extractfile(member)
                if content is None:
                    raise RestoreError(f"Cannot read archive member: {name}")
                with content, target.open("xb") as output:
                    for chunk in iter(lambda source=content: source.read(CHUNK_SIZE), b""):
                        digest.update(chunk)
                        size += len(chunk)
                        output.write(chunk)
                if size != entry["size_bytes"] or digest.hexdigest() != entry["sha256"]:
                    raise RestoreError(f"Archive member hash mismatch: {name}")
                os.chmod(str(target), 0o644)
                seen.add(name)
        # Normally already at EOF; explicitly finish validation of the gzip stream/trailer.
        if bounded.read(CHUNK_SIZE):
            raise RestoreError("Unexpected trailing data after archive")
    missing = sorted(set(entries) - seen)
    if missing:
        raise RestoreError("Archive is missing manifest files: {}".format(", ".join(missing[:5])))


def check_destination(project, name, entry):
    """Inspect every existing parent, including case aliases and symlinks."""
    components = name.split("/")
    current = project
    for index, component in enumerate(components):
        # The previous iteration established that current is an actual directory.
        with os.scandir(str(current)) as children:
            aliases = [child.name for child in children if canonical(child.name) == canonical(component)]
        if aliases and aliases != [component]:
            raise RestoreError(f"Existing case/Unicode alias at {current}: {aliases}")
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            return False
        is_last = index == len(components) - 1
        if not is_last:
            if not stat.S_ISDIR(info.st_mode):
                raise RestoreError(f"Destination parent is not a real directory: {current}")
        else:
            if not stat.S_ISREG(info.st_mode):
                raise RestoreError(f"Destination is a link or non-regular file: {current}")
            try:
                verify_file(current, entry)
            except RestoreError as exc:
                raise RestoreError(f"Existing file differs; refusing to overwrite: {current}") from exc
            return True
    return False


def create_parents(project, name, created_directories):
    current = project
    for component in name.split("/")[:-1]:
        current = current / component
        try:
            current.mkdir()
            created_directories.append((current, current.lstat()))
        except FileExistsError:
            if not stat.S_ISDIR(current.lstat().st_mode):
                raise RestoreError(f"Destination parent is not a real directory: {current}")


def link_staged_file(project, name, source, created_directories):
    """Use anchored, no-follow directory descriptors where the platform supports them."""
    anchored = (os.name == "posix" and os.open in os.supports_dir_fd
                and os.mkdir in os.supports_dir_fd and os.link in os.supports_dir_fd
                and hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW"))
    if not anchored:
        create_parents(project, name, created_directories)
        # Recheck every parent immediately before the exclusive installation.
        current = project
        for component in name.split("/")[:-1]:
            current = current / component
            if not stat.S_ISDIR(current.lstat().st_mode):
                raise RestoreError(f"Destination parent is not a real directory: {current}")
        os.link(str(source), str(project.joinpath(*name.split("/"))))
        return

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(str(project), flags)
    current = project
    try:
        for component in name.split("/")[:-1]:
            with os.scandir(descriptor) as children:
                aliases = [child.name for child in children
                           if canonical(child.name) == canonical(component)]
            if aliases and aliases != [component]:
                raise RestoreError(f"Existing case/Unicode alias at {current}: {aliases}")
            current = current / component
            try:
                child_descriptor = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(component, dir_fd=descriptor)
                    info = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
                    created_directories.append((current, info))
                except FileExistsError:
                    pass
                child_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child_descriptor
        leaf = name.split("/")[-1]
        with os.scandir(descriptor) as children:
            aliases = [child.name for child in children
                       if canonical(child.name) == canonical(leaf)]
        if aliases and aliases != [leaf]:
            raise RestoreError(f"Existing case/Unicode alias at {current}: {aliases}")
        os.link(str(source), leaf, dst_dir_fd=descriptor, follow_symlinks=False)
    finally:
        os.close(descriptor)


def install_staged(project, staged, entries):
    # Preflight all destinations before adding any permanent raw files.
    skipped = {name for name, entry in entries.items() if check_destination(project, name, entry)}
    created_files = []
    created_directories = []
    try:
        for name, entry in entries.items():
            if name in skipped:
                continue
            if check_destination(project, name, entry):
                skipped.add(name)
                continue
            destination = project.joinpath(*name.split("/"))
            source = staged.joinpath(*name.split("/"))
            try:
                # Staging is on the same filesystem. link() is atomic and never overwrites.
                link_staged_file(project, name, source, created_directories)
            except FileExistsError:
                if check_destination(project, name, entry):
                    skipped.add(name)
                    continue
                raise
            created_files.append(destination)
    except BaseException:
        # Roll back files introduced by this attempt; never remove a pre-existing file.
        for destination in reversed(created_files):
            source = staged / destination.relative_to(project)
            try:
                if os.path.samestat(destination.lstat(), source.lstat()):
                    destination.unlink()
            except OSError:
                pass
        for directory, created_info in reversed(created_directories):
            try:
                if os.path.samestat(directory.lstat(), created_info):
                    directory.rmdir()
            except OSError:
                pass
        raise
    return len(created_files), len(skipped)


def restore(parts_dir, project_dir):
    project = Path(project_dir).resolve(strict=True)
    parts = Path(parts_dir).resolve(strict=True)
    if not project.is_dir() or not parts.is_dir():
        raise RestoreError("Project and parts paths must be existing directories")
    manifest, entries = load_manifest(parts, project)
    with tempfile.TemporaryDirectory(prefix=".raw-restore-", dir=str(project)) as temporary:
        work = Path(temporary)
        combined = work / "verified.tar.gz"
        staged = work / "files"
        concatenate_parts(parts, combined, manifest)
        stage_archive(combined, staged, manifest, entries)
        restored, skipped = install_staged(project, staged, entries)
    return {
        "status": "pass",
        "paper": manifest["paper"],
        "verified_parts": len(manifest["parts"]),
        "verified_files": len(entries),
        "verified_raw_bytes": manifest["archive"]["unpacked_size_bytes"],
        "restored_files": restored,
        "existing_identical_files_skipped": skipped,
        "project_dir": str(project),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts-dir", type=Path, required=True,
                        help="Directory containing raw-data-manifest.json and all archive parts")
    parser.add_argument("--project-dir", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Existing project root (default: parent of this script's directory)")
    args = parser.parse_args()
    try:
        result = restore(args.parts_dir, args.project_dir)
    except (RestoreError, OSError, tarfile.TarError, EOFError, ValueError, zlib.error) as exc:
        print(f"Raw-data restore failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
