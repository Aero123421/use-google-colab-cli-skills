# Reliable Google Colab CLI Skill

[日本語](README.ja.md) · [SKILL.md](skills/colab-cli-reliable/SKILL.md) · [MIT License](LICENSE)

An open-source agent skill for operating the official **google-colab-cli** reliably while minimizing total Colab Compute Units (**CU**) to a verified result at the required quality and deadline.

- **Skill created:** `2026-11-13T09:25:10Z` (`2026-11-13 18:25:10 JST`, initial saved version)
- **Research reviewed:** `2026-11-13` (CLI/GPU operational updates: `2026-11-16`)
- **Scope:** Community workflow and offline helpers — not an official Google skill or replacement CLI. No Colab runtime was allocated or CU spent during research or testing.

---

## Quick Start

```bash
git clone https://github.com/Aero123421/use-google-colab-cli-skills.git
```

Copy the **entire** [`skills/colab-cli-reliable`](skills/colab-cli-reliable/SKILL.md) directory into your agent's skill folder (keeping `SKILL.md`, `references/`, `scripts/`, and `assets/` together), or point the agent directly at [SKILL.md](skills/colab-cli-reliable/SKILL.md). Installing and authenticating `google-colab-cli` are separate prerequisites; see [CLI operations](skills/colab-cli-reliable/references/operations.md).

**Example prompt:**

> Use `colab-cli-reliable` to prepare this workload, compare authorized GPU/TPU options within my CU and time budget, recover safely from disconnects, verify durable outputs, and release the runtime.

---

## Execution Lifecycle

Changing hardware replaces the runtime: **a CPU VM's `/content`, packages, and kernel state do not transfer to a GPU or TPU VM** ([Colab maintainer note](https://github.com/googlecolab/colab-vscode/discussions/265)).

```text
Local prep & bundle dry-run ─▶ (Optional CPU / durable handoff) ─▶ Allocate GPU/TPU
   ─▶ Asset + 1-step preflight ─▶ Compute & save/manifest ─▶ Rescue/retrieve & release
   ─▶ Target-CPU export, quantization, parity & reporting
```

1. **Validate locally first:** Clean data, record hashes, and test-extract any minimal source bundle into a temp directory (`--help`, imports, and post-check scripts) at 0 CU.
2. **Stage durably if needed:** Upload inputs and checksums to Drive (skip an intermediate Colab CPU VM if local upload works; tiny jobs may be cheaper via direct upload after allocation). With `colab upload`, always target an existing flat path like `/content/` and move files into subdirectories on the VM.
3. **Verify hardware & run preflight:** On the new GPU/TPU VM, confirm actual device/topology, load every required OS asset/font/file by real path/API (not base package names), and run a 1-step forward/backward + save/restore smoke check before full execution.
4. **Save first, then validate:** Write trained weights and SHA-256 manifests *before* optional downstream checks or test suites; transfer large artifacts in verified chunks.
5. **Rescue & release before CPU post-work:** On any completion, error, timeout, or interrupt, rescue recoverable checkpoints/logs first, `stop` only the owned session, verify removal in `sessions` and record `usage`, then run ONNX export, INT8 quantization calibration, target-CPU parity checks, tests, and reporting locally.

---

## Core Rules

| Area | Rule |
| --- | --- |
| **Cost accounting** | Compare total allocated CU (`Σ rate × seconds / 3600`) across setup, transfer, compile, compute, save, and idle time at equal quality and exact output count. |
| **File transfers** | `colab upload` does not create missing parent dirs (can 500 on Contents API); upload flatly to `/content/`. Split large downloads into chunks + SHA-256 manifest. |
| **Long jobs** | Prefer a detached VM worker writing atomic `progress.json` + bounded periodic polling over a single multi-hour WebSocket; separate heartbeat stall detection from throughput-derived stage deadlines. |
| **Checkpoints & resume** | Split multi-stage runs into per-stage verified checkpoints so restarts can re-inject completed weights and skip finished stages. |
| **Disconnects (UNKNOWN)** | Never treat exit code `0`, local `IDLE`, or `colab log` as proof of completion. Inspect `progress.json` / `sessions` first; never blind-retry or reuse the same session name for `new`. |
| **GPU / TPU / CPU split** | Keep accelerators on accelerator math + minimal save checks; move export, quantization calibration, and strict CPU parity checks off GPU (avoiding server vs. target CPU rounding drift). |
| **Release check** | Confirm owned endpoint removal via `colab --auth=adc sessions` and log `colab --auth=adc usage` (note: `usage` is account-wide, not per-job). |

Details, dated upstream caveats, and primary-source links live in `references/` so [SKILL.md](skills/colab-cli-reliable/SKILL.md) stays compact.

---

## Local Offline Helpers

Both scripts use only the Python standard library and make **no network or Colab API calls**.

### 1. CU Comparison (`compare_cu.py`)

Compares supplied candidate observations against quality, exact valid-output count, CU ceiling, and deadline:

```bash
python3 skills/colab-cli-reliable/scripts/compare_cu.py \
  --input skills/colab-cli-reliable/assets/cost-comparison.example.json \
  --max-cus 0.7 --deadline-seconds 1800 --json
```

> **Note:** Rates and timings in [cost-comparison.example.json](skills/colab-cli-reliable/assets/cost-comparison.example.json) are **fictional**. Replace them with observed measurements. See [cost-and-staging.md](skills/colab-cli-reliable/references/cost-and-staging.md#compare-recorded-candidates-locally) for the schema.

### 2. Chunked Artifact Manifest (`chunk_manifest.py`)

Because `colab download` buffers entire files as JSON/Base64 in memory, split large outputs on the VM into fixed-size chunks with SHA-256 manifests and verify/reassemble them locally:

```bash
python3 skills/colab-cli-reliable/scripts/chunk_manifest.py split --input model.pt --out-dir chunks --chunk-mib 16
python3 skills/colab-cli-reliable/scripts/chunk_manifest.py join --manifest chunks/model.pt.manifest.json --output model.pt
```

---

## Contents

| File | Purpose |
| --- | --- |
| [SKILL.md](skills/colab-cli-reliable/SKILL.md) | Compact 12-rule procedural skill instructions |
| [Cost & staging](skills/colab-cli-reliable/references/cost-and-staging.md) | CU math, CPU handoff, bundle dry-run, preflight, stage-skip, Drive |
| [GPU guide](skills/colab-cli-reliable/references/gpu.md) | Preflight, throughput, numerical checks, save-before-validate, CPU parity |
| [TPU guide](skills/colab-cli-reliable/references/tpu.md) | Topology checks, shape stability, pipelines, optional CPU cross-compile |
| [CLI operations](skills/colab-cli-reliable/references/operations.md) | Dated CLI/auth/upload/chunking/long-job/recovery notes (Japanese) |
| [Compatibility](skills/colab-cli-reliable/references/compatibility.md) | Dated CLI/framework support and TorchTPU migration notes |
| [compare_cu.py](skills/colab-cli-reliable/scripts/compare_cu.py) / [tests](tests/test_compare_cu.py) | Offline CU comparison helper and unit tests |
| [chunk_manifest.py](skills/colab-cli-reliable/scripts/chunk_manifest.py) / [tests](tests/test_chunk_manifest.py) | Offline chunk split/verify/join helper and unit tests |

---

## Development & License

Run the offline test suite without generating bytecode:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

- **Evidence policy:** Recommendations cite official Colab, Cloud, JAX, PyTorch, and TensorFlow sources; issue threads and field reports are labeled as dated observations, not SLA guarantees. See [AGENTS.md](AGENTS.md) for maintenance rules.
- **License:** [MIT](LICENSE), copyright 2026 Aero123421. Upstream tools and docs retain their respective licenses; `google-colab-cli` source code is not bundled.
