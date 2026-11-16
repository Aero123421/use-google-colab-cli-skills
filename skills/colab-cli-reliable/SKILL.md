---
name: colab-cli-reliable
description: Operate the official Google Colab CLI reliably and minimize compute units (CU) for CPU, GPU and TPU jobs. Use for authentication, uploads, CPU-to-accelerator staging, Google Drive, training/inference performance, long jobs, disconnect recovery, concurrent agents and artifact retrieval. Colab CLIの安定運用・TPU活用・CU節約。
---

# Reliable, economical Colab CLI

Created: **2026-11-13T09:25:10Z** (18:25:10 JST; initial saved skill). Research reviewed: **2026-11-13** (operational updates: **2026-11-16**).

Optimize **total CU to a verified result at the required quality and deadline**. Treat a runtime as disposable. CU means Colab Compute Units throughout this skill.

## Before allocating

1. Read [CLI operations](references/operations.md) for authentication, current flags and known failures. Check `colab version` and command help; pin a tested version and never upgrade during a job. Use explicit, verified authentication; complete account/Drive consent before unattended work. Never print credentials.
2. Record the permitted devices, CU/time budget, tuning budget, quality target, durable destination and cancellation policy. Reuse existing authorization. Give each job/attempt and session a unique ID; record its endpoint. Explicitly target the session and serialize mutations through one owner.
3. Prepare and validate data/code on local CPU, or a Colab CPU runtime when useful. Prefer direct upload to durable storage. Extract and dry-run any source bundle locally (including auxiliary/post-check scripts) before allocating. **A hardware change creates a new VM: `/content`, packages and kernel state do not transfer.** Copy inputs and a checksum manifest to durable storage, verify them, then release CPU and allocate GPU/TPU. When using `colab upload`, upload flatly into an existing directory (such as `/content/`) and place subdirectories on the VM. Do not assume Colab CPU/high-RAM costs zero CU. Read [cost and staging](references/cost-and-staging.md).

## Use the accelerator efficiently

4. Allocate only when inputs are ready. Inspect the actual device, memory, topology and framework/backend compatibility; reject unintended CPU fallback. Never assume a TPU device count. Verify actual required runtime assets (OS packages, fonts, binaries, files—not base package presence alone) and pass a minimal 1-step forward/backward plus save/restore preflight before launching full training. Stage the working set locally or stream shards with bounded prefetch; avoid training directly on many small Drive files.
5. Run a bounded representative pilot. Include allocation, install, transfers, compilation, computation, evaluation and saving in cost; distinguish cold and warm timing and synchronize asynchronous work at measurement boundaries. Compare equal useful work at equal quality. Measure current rates; account-wide usage is not a per-job meter. Use [the local CU calculator](scripts/compare_cu.py) when comparing recorded candidates.
6. Tune the bottleneck using [GPU guidance](references/gpu.md) or [TPU guidance](references/tpu.md). Stabilize shapes/buckets, choose a batch with memory headroom, overlap input work, and reduce host synchronizations. Test mixed precision against quality/NaN checks. Use compilation, cache reuse, distribution or recomputation only when their overhead pays back within this workload. Limit tuning expenditure.

## Run with recoverable evidence

7. For valuable work, use explicit allocate → execute → verify → release (with `run`, preserve the VM with `--keep` until verified). For multi-hour jobs, prefer a detached VM worker writing atomic `progress.json` and logs paired with bounded periodic status checks rather than relying on a single long-lived WebSocket stream. Separate progress-stall (heartbeat) timeouts from stage completion deadlines; derive stage deadlines from measured early throughput rather than short fixed constants. No dummy keepalive or quota bypass.
8. Emit final weights, checkpoints and SHA-256 manifests **immediately after training completes—before optional downstream validation or tests**. Split multi-stage pipelines into per-stage verified checkpoints so restarts can re-inject completed weights and skip finished stages. Transfer large artifacts as fixed-size chunks with a SHA-256 manifest ([chunk helper](scripts/chunk_manifest.py)) and verify after reassembly. Write small `progress.json`, logs and `result.json` with job/attempt ID, code/input identity, status and artifact hashes; a local file or asynchronous save alone is not durable evidence.
9. Accept success only from matching completion evidence and verified artifacts. Exit code 0, local IDLE, notebook history, or a disconnected client alone proves neither success nor remote termination.

## Recover and release

10. On disconnect, failure, timeout or interrupt: first inspect `progress.json`/`sessions` if remote state is unverified (never blind-retry or reuse the same session name for `new`), and **rescue-download and hash-verify any completed or intermediate checkpoints and logs before error handling or cleanup**. Follow the configured cancellation/budget policy when halting work.
11. Keep accelerators focused on computation and minimal save checks; release the runtime before CPU-bound export, quantization calibration, strict deployment CPU parity verification, full test suites or reporting. On completion or teardown, rescue/verify outputs outside the VM, `stop` **only the owned session**, confirm its removal in `sessions`, check `usage` and record release evidence in the local ledger.
12. Report result evidence, location, actual/estimated CU with attribution limits, quality, elapsed time and release status. For UNKNOWN, report the retained endpoint, budget exposure and next decision deadline. Never label unmeasured speedups or illustrative tariffs as observations.

## Load details only when needed

- [Cost, CPU staging, Drive and calculator schema](references/cost-and-staging.md)
- [GPU throughput and numerical correctness](references/gpu.md)
- [TPU shapes, compilation, input pipelines and backends](references/tpu.md)
- [CLI authentication, failure recovery and dated issue evidence](references/operations.md)
- [Dated TPU/framework compatibility](references/compatibility.md)
- [Local CU comparison](scripts/compare_cu.py) and [chunk manifest](scripts/chunk_manifest.py) helpers
