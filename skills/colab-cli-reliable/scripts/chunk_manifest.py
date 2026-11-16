#!/usr/bin/env python3
"""Split, verify, and reassemble large artifacts using fixed-size chunks and SHA-256 manifests.

Pure standard-library, offline helper intended for both remote Colab VM preparation
(before chunked `colab download`) and local reassembly/verification.
Exit codes: 0 = success, 1 = missing chunk or integrity mismatch, 2 = invalid input/manifest.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

IO_BUFFER_BYTES = 1024 * 1024
DEFAULT_CHUNK_MIB = 16
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class ChunkIntegrityError(Exception):
    """Raised when a chunk is missing, truncated, oversized, or fails SHA-256."""


def reject_constant(value):
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def safe_filename(name, field="filename"):
    if not isinstance(name, str) or not name or name != name.strip():
        raise ValueError(f"{field} must be a nonempty filename without surrounding whitespace")
    if "/" in name or "\\" in name or name in (".", "..") or Path(name).name != name:
        raise ValueError(f"{field} must be a plain filename without path separators: {name!r}")
    return name


def require_int(value, field, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def require_sha256(value, field):
    if not isinstance(value, str) or not HEX64_RE.fullmatch(value):
        raise ValueError(f"{field} must be a 64-character lowercase SHA-256 hex digest")
    return value


def atomic_write_bytes(target_path: Path, write_fn):
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target_path.parent, prefix=f".{target_path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            result = write_fn(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, target_path)
        return result
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_json(target_path: Path, payload: dict):
    encoded = (json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    atomic_write_bytes(target_path, lambda stream: stream.write(encoded))


def split_file(
    input_path: Path,
    out_dir: Path,
    chunk_size_bytes: int,
    manifest_path: Path | None = None,
    prefix: str | None = None,
) -> dict:
    if not input_path.is_file():
        raise ValueError(f"input file does not exist or is not a regular file: {input_path}")
    chunk_size_bytes = require_int(chunk_size_bytes, "chunk_size_bytes", 1)
    artifact_name = safe_filename(input_path.name, "artifact_name")
    chunk_prefix = safe_filename(prefix if prefix is not None else f"{artifact_name}.part", "prefix")
    out_dir.mkdir(parents=True, exist_ok=True)
    resolved_manifest = manifest_path if manifest_path is not None else (out_dir / f"{artifact_name}.manifest.json")

    total_hasher = hashlib.sha256()
    total_bytes = 0
    chunks = []
    index = 0

    with input_path.open("rb") as src:
        while True:
            chunk_name = f"{chunk_prefix}.{index:04d}"
            chunk_path = out_dir / chunk_name
            chunk_hasher = hashlib.sha256()
            chunk_bytes = 0
            eof = False

            def write_chunk(dst):
                nonlocal chunk_bytes, total_bytes, eof
                remaining = chunk_size_bytes
                while remaining > 0:
                    data = src.read(min(IO_BUFFER_BYTES, remaining))
                    if not data:
                        eof = True
                        break
                    dst.write(data)
                    chunk_hasher.update(data)
                    total_hasher.update(data)
                    n = len(data)
                    chunk_bytes += n
                    total_bytes += n
                    remaining -= n

            # Peek at least 1 byte before creating a chunk file so exact multiples don't create an empty trailing chunk.
            first = src.read(min(IO_BUFFER_BYTES, chunk_size_bytes))
            if not first:
                break

            def write_nonempty_chunk(dst):
                nonlocal chunk_bytes, total_bytes, eof
                dst.write(first)
                chunk_hasher.update(first)
                total_hasher.update(first)
                n0 = len(first)
                chunk_bytes += n0
                total_bytes += n0
                remaining = chunk_size_bytes - n0
                while remaining > 0:
                    data = src.read(min(IO_BUFFER_BYTES, remaining))
                    if not data:
                        eof = True
                        break
                    dst.write(data)
                    chunk_hasher.update(data)
                    total_hasher.update(data)
                    n = len(data)
                    chunk_bytes += n
                    total_bytes += n
                    remaining -= n

            atomic_write_bytes(chunk_path, write_nonempty_chunk)
            chunks.append(
                {
                    "index": index,
                    "filename": chunk_name,
                    "size_bytes": chunk_bytes,
                    "sha256": chunk_hasher.hexdigest(),
                }
            )
            index += 1
            if eof:
                break

    manifest = {
        "schema_version": 1,
        "artifact_name": artifact_name,
        "total_bytes": total_bytes,
        "sha256": total_hasher.hexdigest(),
        "chunk_size_bytes": chunk_size_bytes,
        "chunks": chunks,
    }
    atomic_write_json(resolved_manifest, manifest)
    return {
        "status": "ok",
        "action": "split",
        "input": str(input_path),
        "out_dir": str(out_dir),
        "manifest": str(resolved_manifest),
        "artifact_name": artifact_name,
        "total_bytes": total_bytes,
        "sha256": manifest["sha256"],
        "chunk_size_bytes": chunk_size_bytes,
        "chunk_count": len(chunks),
    }


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.is_file():
        raise ValueError(f"manifest file does not exist: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream, parse_constant=reject_constant, object_pairs_hook=unique_object)
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    safe_filename(manifest.get("artifact_name"), "artifact_name")
    total_bytes = require_int(manifest.get("total_bytes"), "total_bytes", 0)
    require_int(manifest.get("chunk_size_bytes"), "chunk_size_bytes", 1)
    require_sha256(manifest.get("sha256"), "sha256")

    chunks = manifest.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("chunks must be a JSON array")

    seen_names = set()
    sum_bytes = 0
    for expected_index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError(f"chunks[{expected_index}] must be an object")
        idx = require_int(chunk.get("index"), f"chunks[{expected_index}].index", 0)
        if idx != expected_index:
            raise ValueError(f"chunks[{expected_index}].index must be {expected_index}, got {idx}")
        fname = safe_filename(chunk.get("filename"), f"chunks[{expected_index}].filename")
        if fname in seen_names:
            raise ValueError(f"duplicate chunk filename in manifest: {fname}")
        seen_names.add(fname)
        size = require_int(chunk.get("size_bytes"), f"chunks[{expected_index}].size_bytes", 1)
        require_sha256(chunk.get("sha256"), f"chunks[{expected_index}].sha256")
        sum_bytes += size

    if sum_bytes != total_bytes:
        raise ValueError(f"sum of chunk sizes ({sum_bytes}) does not match total_bytes ({total_bytes})")
    if total_bytes == 0 and chunks:
        raise ValueError("total_bytes is 0 but chunks array is non-empty")
    if total_bytes > 0 and not chunks:
        raise ValueError("total_bytes > 0 but chunks array is empty")
    return manifest


def _stream_verified_chunks(manifest: dict, base_dir: Path, dst_stream=None) -> tuple[int, str]:
    total_hasher = hashlib.sha256()
    total_read = 0
    for chunk in manifest["chunks"]:
        chunk_path = base_dir / chunk["filename"]
        if not chunk_path.is_file():
            raise ChunkIntegrityError(f"missing chunk file: {chunk_path}")
        actual_size = chunk_path.stat().st_size
        if actual_size != chunk["size_bytes"]:
            raise ChunkIntegrityError(
                f"chunk size mismatch for {chunk['filename']}: expected {chunk['size_bytes']}, got {actual_size}"
            )
        chunk_hasher = hashlib.sha256()
        chunk_read = 0
        with chunk_path.open("rb") as src:
            while True:
                data = src.read(IO_BUFFER_BYTES)
                if not data:
                    break
                chunk_hasher.update(data)
                total_hasher.update(data)
                chunk_read += len(data)
                if dst_stream is not None:
                    dst_stream.write(data)
        if chunk_read != chunk["size_bytes"]:
            raise ChunkIntegrityError(
                f"chunk read length mismatch for {chunk['filename']}: expected {chunk['size_bytes']}, got {chunk_read}"
            )
        digest = chunk_hasher.hexdigest()
        if digest != chunk["sha256"]:
            raise ChunkIntegrityError(
                f"chunk SHA-256 mismatch for {chunk['filename']}: expected {chunk['sha256']}, got {digest}"
            )
        total_read += chunk_read

    if total_read != manifest["total_bytes"]:
        raise ChunkIntegrityError(
            f"total byte length mismatch: expected {manifest['total_bytes']}, got {total_read}"
        )
    total_digest = total_hasher.hexdigest()
    if total_digest != manifest["sha256"]:
        raise ChunkIntegrityError(
            f"overall artifact SHA-256 mismatch: expected {manifest['sha256']}, got {total_digest}"
        )
    return total_read, total_digest


def verify_chunks(manifest_path: Path, chunks_dir: Path | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    base_dir = chunks_dir if chunks_dir is not None else manifest_path.parent
    total_read, total_digest = _stream_verified_chunks(manifest, base_dir, dst_stream=None)
    return {
        "status": "ok",
        "action": "verify",
        "manifest": str(manifest_path),
        "chunks_dir": str(base_dir),
        "artifact_name": manifest["artifact_name"],
        "total_bytes": total_read,
        "sha256": total_digest,
        "chunk_count": len(manifest["chunks"]),
    }


def join_chunks(manifest_path: Path, output_path: Path, chunks_dir: Path | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    base_dir = chunks_dir if chunks_dir is not None else manifest_path.parent

    def write_joined(dst):
        return _stream_verified_chunks(manifest, base_dir, dst_stream=dst)

    total_read, total_digest = atomic_write_bytes(output_path, write_joined)
    return {
        "status": "ok",
        "action": "join",
        "manifest": str(manifest_path),
        "chunks_dir": str(base_dir),
        "output": str(output_path),
        "artifact_name": manifest["artifact_name"],
        "total_bytes": total_read,
        "sha256": total_digest,
        "chunk_count": len(manifest["chunks"]),
    }


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    split_p = subparsers.add_parser("split", help="Split a file into fixed-size chunks and write a SHA-256 manifest")
    split_p.add_argument("--input", required=True, type=Path, help="Source file path")
    split_p.add_argument("--out-dir", required=True, type=Path, help="Output directory for chunks")
    size_group = split_p.add_mutually_exclusive_group()
    size_group.add_argument("--chunk-bytes", type=int, help="Exact chunk size in bytes")
    size_group.add_argument("--chunk-mib", type=int, default=DEFAULT_CHUNK_MIB, help=f"Chunk size in MiB (default: {DEFAULT_CHUNK_MIB})")
    split_p.add_argument("--manifest", type=Path, help="Manifest path (default: <out-dir>/<name>.manifest.json)")
    split_p.add_argument("--prefix", help="Chunk filename prefix (default: <name>.part)")
    split_p.add_argument("--json", action="store_true", help="Write machine-readable JSON")

    verify_p = subparsers.add_parser("verify", help="Verify chunks and combined SHA-256 against a manifest")
    verify_p.add_argument("--manifest", required=True, type=Path, help="Manifest JSON path")
    verify_p.add_argument("--chunks-dir", type=Path, help="Directory holding chunk files (default: manifest directory)")
    verify_p.add_argument("--json", action="store_true", help="Write machine-readable JSON")

    join_p = subparsers.add_parser("join", help="Verify chunks and atomically reassemble the artifact")
    join_p.add_argument("--manifest", required=True, type=Path, help="Manifest JSON path")
    join_p.add_argument("--chunks-dir", type=Path, help="Directory holding chunk files (default: manifest directory)")
    join_p.add_argument("--output", required=True, type=Path, help="Output artifact path")
    join_p.add_argument("--json", action="store_true", help="Write machine-readable JSON")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    use_json = getattr(args, "json", False)
    try:
        if args.command == "split":
            chunk_bytes = args.chunk_bytes if args.chunk_bytes is not None else require_int(args.chunk_mib, "chunk_mib", 1) * 1024 * 1024
            result = split_file(args.input, args.out_dir, chunk_bytes, manifest_path=args.manifest, prefix=args.prefix)
        elif args.command == "verify":
            result = verify_chunks(args.manifest, chunks_dir=args.chunks_dir)
        elif args.command == "join":
            result = join_chunks(args.manifest, args.output, chunks_dir=args.chunks_dir)
        else:
            raise ValueError(f"unknown command: {args.command}")
    except ChunkIntegrityError as exc:
        err = {"status": "integrity_error", "error": str(exc)}
        if use_json:
            print(json.dumps(err, ensure_ascii=False, allow_nan=False))
        else:
            print(f"Integrity error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        err = {"status": "invalid_input", "error": str(exc)}
        if use_json:
            print(json.dumps(err, ensure_ascii=False, allow_nan=False))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2

    if use_json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    else:
        print(
            f"{result['action']}: {result['artifact_name']} "
            f"({result['total_bytes']} bytes, {result['chunk_count']} chunks, sha256={result['sha256']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
