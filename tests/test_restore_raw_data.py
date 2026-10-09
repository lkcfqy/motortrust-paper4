"""Synthetic, isolated safety checks for the public raw-data restore helper."""

import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import restore_raw_data as restore


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="motortrust-restore-test-")
        self.root = Path(self.temporary.name)
        self.parts = self.root / "assets"
        self.project = self.root / "project"
        self.parts.mkdir()
        self.project.mkdir()
        self.code = self.project / "code.py"
        self.code.write_bytes(b"code must remain unchanged\n")
        (self.project / "docs").mkdir()
        (self.project / "docs" / "readme.md").write_bytes(b"docs must remain unchanged\n")

    def tearDown(self):
        self.assertEqual(self.code.read_bytes(), b"code must remain unchanged\n")
        self.assertEqual((self.project / "docs" / "readme.md").read_bytes(), b"docs must remain unchanged\n")
        self.assertFalse(list(self.project.glob(".raw-restore-*")))
        self.temporary.cleanup()

    def package(self, members=None, manifest_files=None, compressed=None):
        if members is None:
            members = [("data/raw/example/input.csv", b"a,b\n1,2\n", tarfile.REGTYPE),
                       ("data/raw/example/LICENSE", b"Original dataset license\n", tarfile.REGTYPE)]
        if compressed is None:
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data, kind in members:
                    info = tarfile.TarInfo(name)
                    info.type = kind
                    info.mode = 0o644
                    if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                        info.linkname = "../../code.py"
                    else:
                        info.size = len(data)
                    archive.addfile(info, io.BytesIO(data) if info.isreg() else None)
            compressed = gzip.compress(buffer.getvalue(), mtime=0)
        if manifest_files is None:
            manifest_files = [
                {"path": name, "size_bytes": len(data), "sha256": digest(data)}
                for name, data, _ in members
            ]
        parts = []
        part_size = max(1, len(compressed) // 3)
        for index, offset in enumerate(range(0, len(compressed), part_size), 1):
            data = compressed[offset:offset + part_size]
            name = f"test.tar.gz.part{index:03d}"
            (self.parts / name).write_bytes(data)
            parts.append({"filename": name, "size_bytes": len(data), "sha256": digest(data)})
        manifest = {
            "schema_version": 1, "paper": 4,
            "archive": {"filename": "test.tar.gz", "format": "tar.gz",
                        "size_bytes": len(compressed), "sha256": digest(compressed),
                        "unpacked_size_bytes": sum(entry["size_bytes"] for entry in manifest_files)},
            "parts": parts, "files": manifest_files,
        }
        self.save_manifest(manifest)
        return manifest

    def save_manifest(self, manifest):
        (self.parts / "raw-data-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def assert_rejected_without_new_raw(self, message):
        with self.assertRaisesRegex((restore.RestoreError, OSError, tarfile.TarError, EOFError), message):
            restore.restore(self.parts, self.project)
        self.assertFalse((self.project / "data").exists())

    def test_valid_parts_restore_and_identical_rerun(self):
        manifest = self.package()
        first = restore.restore(self.parts, self.project)
        self.assertEqual(first["restored_files"], 2)
        self.assertEqual(first["verified_parts"], len(manifest["parts"]))
        self.assertEqual((self.project / "data/raw/example/input.csv").read_bytes(), b"a,b\n1,2\n")
        self.assertEqual((self.project / "data/raw/example/LICENSE").read_bytes(), b"Original dataset license\n")
        second = restore.restore(self.parts, self.project)
        self.assertEqual(second["restored_files"], 0)
        self.assertEqual(second["existing_identical_files_skipped"], 2)

    def test_cli_restores_and_prints_verified_counts(self):
        self.package()
        result = subprocess.run([sys.executable, restore.__file__, "--parts-dir", str(self.parts),
                                 "--project-dir", str(self.project)], capture_output=True, text=True,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["verified_files"], 2)

    def test_corrupted_part_is_rejected_before_install(self):
        manifest = self.package()
        path = self.parts / manifest["parts"][1]["filename"]
        content = path.read_bytes()
        path.write_bytes(bytes([content[0] ^ 1]) + content[1:])
        self.assert_rejected_without_new_raw("part hash mismatch")

    def test_truncated_part_is_rejected_before_install(self):
        manifest = self.package()
        path = self.parts / manifest["parts"][0]["filename"]
        path.write_bytes(path.read_bytes()[:-1])
        self.assert_rejected_without_new_raw("part size mismatch")

    def test_missing_part_is_rejected_before_install(self):
        manifest = self.package()
        (self.parts / manifest["parts"][0]["filename"]).unlink()
        self.assert_rejected_without_new_raw("Cannot read required file")

    def test_wrong_part_order_fails_archive_hash(self):
        manifest = self.package()
        manifest["parts"].reverse()
        self.save_manifest(manifest)
        self.assert_rejected_without_new_raw("archive size/hash mismatch")

    def test_member_hash_mismatch_is_rejected(self):
        manifest = self.package()
        manifest["files"][0]["sha256"] = "0" * 64
        self.save_manifest(manifest)
        self.assert_rejected_without_new_raw("member hash mismatch")

    def test_existing_different_file_prevents_every_install(self):
        self.package()
        parent = self.project / "data/raw/example"
        parent.mkdir(parents=True)
        (parent / "LICENSE").write_bytes(b"my own license\n")
        with self.assertRaisesRegex(restore.RestoreError, "refusing to overwrite"):
            restore.restore(self.parts, self.project)
        self.assertEqual((parent / "LICENSE").read_bytes(), b"my own license\n")
        self.assertFalse((parent / "input.csv").exists())

    def test_manifest_traversal_is_rejected(self):
        self.package(members=[("data/raw/../../code.py", b"bad", tarfile.REGTYPE)])
        self.assert_rejected_without_new_raw("relative path component")

    def test_tar_traversal_is_rejected_even_with_safe_manifest(self):
        files = [{"path": "data/raw/example/input.csv", "size_bytes": 3, "sha256": digest(b"bad")}]
        self.package(members=[("../code.py", b"bad", tarfile.REGTYPE)], manifest_files=files)
        self.assert_rejected_without_new_raw("inside data/raw")

    def test_absolute_tar_path_is_rejected(self):
        self.package(members=[("/data/raw/example/input.csv", b"bad", tarfile.REGTYPE)],
                     manifest_files=[{"path": "data/raw/example/input.csv", "size_bytes": 3,
                                      "sha256": digest(b"bad")}])
        self.assert_rejected_without_new_raw("inside data/raw")

    def test_symlink_member_is_rejected(self):
        self.package(members=[("data/raw/example/input.csv", b"", tarfile.SYMTYPE)])
        self.assert_rejected_without_new_raw("ordinary regular files")

    def test_hardlink_member_is_rejected(self):
        self.package(members=[("data/raw/example/input.csv", b"", tarfile.LNKTYPE)])
        self.assert_rejected_without_new_raw("ordinary regular files")

    def test_directory_member_is_rejected(self):
        self.package(members=[("data/raw/example/input.csv", b"", tarfile.DIRTYPE)])
        self.assert_rejected_without_new_raw("ordinary regular files")

    def test_duplicate_tar_member_is_rejected(self):
        member = ("data/raw/example/input.csv", b"bad", tarfile.REGTYPE)
        self.package(members=[member, member],
                     manifest_files=[{"path": member[0], "size_bytes": 3, "sha256": digest(b"bad")}])
        self.assert_rejected_without_new_raw("Duplicate archive member")

    def test_manifest_file_and_directory_collision_is_rejected(self):
        self.package(members=[("data/raw/example", b"a", tarfile.REGTYPE),
                              ("data/raw/example/input.csv", b"b", tarfile.REGTYPE)])
        self.assert_rejected_without_new_raw("file/directory collision")

    def test_manifest_case_alias_at_parent_is_rejected(self):
        self.package(members=[("data/raw/Example/a.csv", b"a", tarfile.REGTYPE),
                              ("data/raw/example/b.csv", b"b", tarfile.REGTYPE)])
        self.assert_rejected_without_new_raw("Case/Unicode alias")

    def test_manifest_unicode_alias_at_parent_is_rejected(self):
        self.package(members=[("data/raw/caf\u00e9/a.csv", b"a", tarfile.REGTYPE),
                              ("data/raw/cafe\u0301/b.csv", b"b", tarfile.REGTYPE)])
        self.assert_rejected_without_new_raw("Case/Unicode alias")

    def test_manifest_nested_git_is_rejected(self):
        self.package(members=[("data/raw/example/.git/config", b"bad", tarfile.REGTYPE)])
        self.assert_rejected_without_new_raw("Reserved path component")

    def test_manifest_nonportable_names_are_rejected(self):
        for name in ["CON.txt", "x.", "x ", "a:b", "a\\b", "NUL", "COM\u00b9.csv"]:
            with self.subTest(name=name):
                self.package(members=[("data/raw/example/" + name, b"bad", tarfile.REGTYPE)])
                self.assert_rejected_without_new_raw("(Nonportable|Trailing|device)")

    def test_symlink_destination_parent_is_rejected(self):
        self.package()
        (self.project / "data").mkdir()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.project / "data/raw").symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaisesRegex(restore.RestoreError, "not a real directory"):
            restore.restore(self.parts, self.project)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_symlink_destination_file_is_rejected(self):
        self.package()
        parent = self.project / "data/raw/example"
        parent.mkdir(parents=True)
        (parent / "input.csv").symlink_to(self.code)
        with self.assertRaisesRegex(restore.RestoreError, "link or non-regular"):
            restore.restore(self.parts, self.project)
        self.assertFalse((parent / "LICENSE").exists())

    def test_existing_case_alias_is_rejected(self):
        self.package()
        (self.project / "data/raw/Example").mkdir(parents=True)
        with self.assertRaisesRegex(restore.RestoreError, "Existing case/Unicode alias"):
            restore.restore(self.parts, self.project)
        self.assertFalse((self.project / "data/raw/example/input.csv").exists())

    def test_unlisted_tar_member_is_rejected(self):
        members = [("data/raw/example/input.csv", b"bad", tarfile.REGTYPE),
                   ("data/raw/example/extra.csv", b"bad", tarfile.REGTYPE)]
        self.package(members=members,
                     manifest_files=[{"path": members[0][0], "size_bytes": 3, "sha256": digest(b"bad")}])
        self.assert_rejected_without_new_raw("Unlisted")

    def test_missing_tar_member_is_rejected(self):
        manifest = self.package(members=[("data/raw/example/input.csv", b"bad", tarfile.REGTYPE)])
        manifest["files"].append({"path": "data/raw/example/missing.csv", "size_bytes": 0,
                                  "sha256": digest(b"")})
        self.save_manifest(manifest)
        self.assert_rejected_without_new_raw("missing manifest files")

    def test_appended_gzip_tar_is_not_hidden_after_tar_end(self):
        first = io.BytesIO()
        with tarfile.open(fileobj=first, mode="w") as archive:
            info = tarfile.TarInfo("data/raw/example/input.csv")
            info.size = 3
            archive.addfile(info, io.BytesIO(b"bad"))
        second = io.BytesIO()
        with tarfile.open(fileobj=second, mode="w") as archive:
            info = tarfile.TarInfo("data/raw/example/extra.csv")
            info.size = 3
            archive.addfile(info, io.BytesIO(b"bad"))
        compressed = gzip.compress(first.getvalue(), mtime=0) + gzip.compress(second.getvalue(), mtime=0)
        self.package(compressed=compressed,
                     manifest_files=[{"path": "data/raw/example/input.csv", "size_bytes": 3,
                                      "sha256": digest(b"bad")}])
        self.assert_rejected_without_new_raw("Unlisted")

    def test_cli_failure_is_clean_and_nonzero(self):
        manifest = self.package()
        (self.parts / manifest["parts"][0]["filename"]).write_bytes(b"corrupted")
        result = subprocess.run([sys.executable, restore.__file__, "--parts-dir", str(self.parts),
                                 "--project-dir", str(self.project)], capture_output=True, text=True,
                                check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Raw-data restore failed:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.project / "data").exists())

    def test_invalid_gzip_crc_is_rejected_after_part_hashes_pass(self):
        manifest = self.package()
        compressed = b"".join((self.parts / item["filename"]).read_bytes()
                              for item in manifest["parts"])
        broken = compressed[:-8] + bytes([compressed[-8] ^ 1]) + compressed[-7:]
        self.package(compressed=broken, manifest_files=manifest["files"])
        self.assert_rejected_without_new_raw("CRC check failed")

    def test_oversized_tar_padding_is_rejected(self):
        files = [{"path": "data/raw/example/input.csv", "size_bytes": 0, "sha256": digest(b"")}]
        self.package(compressed=gzip.compress(b"\0" * 100000, mtime=0), manifest_files=files)
        self.assert_rejected_without_new_raw("Expanded archive exceeds")

    def test_install_failure_rolls_back_all_new_files(self):
        self.package()
        real_link = restore.os.link
        count = [0]

        def fail_second(*args, **kwargs):
            count[0] += 1
            if count[0] == 2:
                raise OSError("synthetic installation failure")
            return real_link(*args, **kwargs)

        patcher = mock.patch.object(restore.os, "link", side_effect=fail_second)
        with patcher, self.assertRaisesRegex(OSError, "synthetic installation failure"):
            restore.restore(self.parts, self.project)
        self.assertFalse((self.project / "data").exists())

    def test_parent_symlink_swap_after_preflight_cannot_write_into_docs(self):
        self.package()
        parent = self.project / "data/raw/example"
        parent.mkdir(parents=True)
        original = restore.link_staged_file

        def swap_before_install(project, name, source, created_directories):
            parent.rmdir()
            parent.symlink_to(self.project / "docs", target_is_directory=True)
            original(project, name, source, created_directories)

        patcher = mock.patch.object(restore, "link_staged_file", side_effect=swap_before_install)
        with patcher, self.assertRaises((OSError, restore.RestoreError)):
            restore.restore(self.parts, self.project)
        self.assertFalse((self.project / "docs/input.csv").exists())
        self.assertFalse((self.project / "docs/LICENSE").exists())

    def test_committed_manifest_pin_requires_exact_downloaded_bytes(self):
        self.package()
        downloaded = self.parts / "raw-data-manifest.json"
        original = downloaded.read_bytes()
        recovery = self.project / "recovery"
        recovery.mkdir()
        (recovery / "raw-data-manifest.json").write_bytes(original)
        downloaded.write_bytes(original + b"\n")
        self.assert_rejected_without_new_raw("differs from the committed project manifest")
        downloaded.write_bytes(original)
        result = restore.restore(self.parts, self.project)
        self.assertEqual(result["restored_files"], 2)

    def test_oversized_manifest_is_rejected_before_json_parsing(self):
        self.package()
        (self.parts / "raw-data-manifest.json").write_bytes(b" " * (restore.MAX_MANIFEST_BYTES + 1))
        self.assert_rejected_without_new_raw("16 MiB limit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
