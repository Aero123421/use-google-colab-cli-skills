"""Offline behavioral checks for chunk_manifest.py."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(os.environ.get(
    "COLAB_CHUNK_SCRIPT",
    str(Path(__file__).resolve().parents[1] / "skills/colab-cli-reliable/scripts/chunk_manifest.py"),
))
SPEC = importlib.util.spec_from_file_location("chunk_manifest", SCRIPT)
CM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CM)


class ChunkManifestTests(unittest.TestCase):
    def test_split_verify_join_roundtrip_exact_and_remainder(self):
        for size, chunk_size in ((0, 1024), (1, 1024), (1024, 512), (2503, 512)):
            with self.subTest(size=size, chunk_size=chunk_size), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                src = root / "weights.pt"
                payload = bytes((i * 37 + 13) % 256 for i in range(size))
                src.write_bytes(payload)

                chunks_dir = root / "chunks"
                split_res = CM.split_file(src, chunks_dir, chunk_size)
                expected_chunks = (size + chunk_size - 1) // chunk_size if size else 0
                self.assertEqual(split_res["chunk_count"], expected_chunks)
                self.assertEqual(split_res["total_bytes"], size)
                self.assertEqual(split_res["sha256"], hashlib.sha256(payload).hexdigest())

                manifest_path = Path(split_res["manifest"])
                verify_res = CM.verify_chunks(manifest_path)
                self.assertEqual(verify_res["total_bytes"], size)

                out = root / "reconstructed" / "weights.pt"
                join_res = CM.join_chunks(manifest_path, out)
                self.assertEqual(join_res["sha256"], split_res["sha256"])
                self.assertEqual(out.read_bytes(), payload)

    def test_corrupt_missing_or_truncated_chunk_fails_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "model.bin"
            src.write_bytes(b"A" * 500 + b"B" * 500 + b"C" * 100)
            chunks_dir = root / "chunks"
            res = CM.split_file(src, chunks_dir, 500)
            manifest_path = Path(res["manifest"])
            out = root / "existing.bin"
            out.write_bytes(b"keep-me")

            # Corrupt 1 byte without changing length
            c1 = chunks_dir / "model.bin.part.0001"
            orig = c1.read_bytes()
            c1.write_bytes(b"X" + orig[1:])
            with self.assertRaises(CM.ChunkIntegrityError):
                CM.verify_chunks(manifest_path)
            with self.assertRaises(CM.ChunkIntegrityError):
                CM.join_chunks(manifest_path, out)
            self.assertEqual(out.read_bytes(), b"keep-me")

            # Truncate chunk
            c1.write_bytes(orig[:-1])
            with self.assertRaises(CM.ChunkIntegrityError):
                CM.verify_chunks(manifest_path)

            # Delete chunk
            c1.unlink()
            with self.assertRaises(CM.ChunkIntegrityError):
                CM.verify_chunks(manifest_path)

    def test_overall_sha256_mismatch_even_with_valid_chunk_hashes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "data.bin"
            src.write_bytes(b"hello world")
            res = CM.split_file(src, root / "chunks", 5)
            manifest_path = Path(res["manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(CM.ChunkIntegrityError, "overall artifact SHA-256"):
                CM.verify_chunks(manifest_path)

    def test_invalid_manifests_and_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "data.bin"
            src.write_bytes(b"0123456789")
            res = CM.split_file(src, root / "chunks", 5)
            manifest_path = Path(res["manifest"])
            base = json.loads(manifest_path.read_text(encoding="utf-8"))

            bad_cases = []
            # Path traversal in chunk filename
            m = json.loads(json.dumps(base))
            m["chunks"][0]["filename"] = "../escape.part"
            bad_cases.append(m)

            # Path traversal in artifact_name
            m = json.loads(json.dumps(base))
            m["artifact_name"] = "/etc/passwd"
            bad_cases.append(m)

            # Non-contiguous index
            m = json.loads(json.dumps(base))
            m["chunks"][1]["index"] = 2
            bad_cases.append(m)

            # Duplicate chunk filename
            m = json.loads(json.dumps(base))
            m["chunks"][1]["filename"] = m["chunks"][0]["filename"]
            bad_cases.append(m)

            # Sum mismatch
            m = json.loads(json.dumps(base))
            m["total_bytes"] = 999
            bad_cases.append(m)

            # Boolean size
            m = json.loads(json.dumps(base))
            m["chunks"][0]["size_bytes"] = True
            bad_cases.append(m)

            for i, bad in enumerate(bad_cases):
                with self.subTest(case=i):
                    bad_path = root / f"bad_{i}.json"
                    bad_path.write_text(json.dumps(bad), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        CM.load_manifest(bad_path)

    def test_cli_roundtrip_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "ckpt.pt"
            src.write_bytes(os.urandom(4096))
            chunks_dir = root / "out_chunks"

            split_proc = subprocess.run(
                [sys.executable, str(SCRIPT), "split", "--input", str(src),
                 "--out-dir", str(chunks_dir), "--chunk-bytes", "1500", "--json"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(split_proc.returncode, 0, split_proc.stderr)
            split_json = json.loads(split_proc.stdout)
            manifest = split_json["manifest"]

            joined = root / "joined.pt"
            join_proc = subprocess.run(
                [sys.executable, str(SCRIPT), "join", "--manifest", manifest,
                 "--output", str(joined), "--json"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(join_proc.returncode, 0, join_proc.stderr)
            self.assertEqual(joined.read_bytes(), src.read_bytes())

            # Corrupt chunk -> exit 1
            (chunks_dir / "ckpt.pt.part.0000").write_bytes(b"corrupt")
            verify_fail = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--manifest", manifest, "--json"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(verify_fail.returncode, 1)
            self.assertEqual(json.loads(verify_fail.stdout)["status"], "integrity_error")

            # Duplicate JSON key -> exit 2
            dup_manifest = root / "dup.json"
            dup_manifest.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
            bad_proc = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--manifest", str(dup_manifest), "--json"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(bad_proc.returncode, 2)
            self.assertEqual(json.loads(bad_proc.stdout)["status"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
