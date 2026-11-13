---
name: colab-cli-reliable
description: Operate the official Google Colab CLI reliably and minimize compute units (CU) for CPU, GPU and TPU jobs. Use for authentication, uploads, CPU-to-accelerator staging, Google Drive, training/inference performance, long jobs, disconnect recovery, concurrent agents and artifact retrieval. Colab CLIの安定運用・TPU活用・CU節約。
---

# Reliable, economical Colab CLI

Created: **2026-11-13T09:25:10Z** (18:25:10 JST; initial saved skill). Research reviewed: **2026-11-13**.

Optimize **total CU to a verified result at the required quality and deadline**. Treat a runtime as disposable. CU means Colab Compute Units throughout this skill.

## Before allocating

1. Read [CLI operations](references/operations.md) for authentication, current flags and known failures. Check `colab version` and command help; pin a tested version and never upgrade during a job. Use explicit, verified authentication; complete account/Drive consent before unattended work. Never print credentials.
2. Record the permitted devices, CU/time budget, tuning budget, quality target, durable destination and cancellation policy. Reuse existing authorization. Give each job/attempt and session a unique ID; record its endpoint. Explicitly target the session and serialize mutations through one owner.
3. Prepare and validate data/code on local CPU, or a Colab CPU runtime when useful. Prefer direct upload to durable storage. **A hardware change creates a new VM: `/content`, packages and kernel state do not transfer.** Copy inputs and a checksum manifest to durable storage, verify them, then release CPU and allocate GPU/TPU. Recreate dependencies. Do not assume Colab CPU/high-RAM costs zero CU. Read [cost and staging](references/cost-and-staging.md).

## Use the accelerator efficiently

4. Allocate only when inputs are ready. Inspect the actual device, memory, topology and framework/backend compatibility; reject unintended CPU fallback. Never assume a TPU device count. Stage the working set locally or stream shards with bounded prefetch; avoid training directly on many small Drive files.
5. Run a bounded representative pilot. Include allocation, install, transfers, compilation, computation, evaluation and saving in cost; distinguish cold and warm timing and synchronize asynchronous work at measurement boundaries. Compare equal useful work at equal quality. Measure current rates; account-wide usage is not a per-job meter. Use [the local CU calculator](scripts/compare_cu.py) when comparing recorded candidates.
6. Tune the bottleneck using [GPU guidance](references/gpu.md) or [TPU guidance](references/tpu.md). Stabilize shapes/buckets, choose a batch with memory headroom, overlap input work, and reduce host synchronizations. Test mixed precision against quality/NaN checks. Use compilation, cache reuse, distribution or recomputation only when their overhead pays back within this workload. Limit tuning expenditure.

## Run with recoverable evidence

7. For valuable work, use explicit allocate → execute → verify → release. With current `run`, preserve the VM using `--keep` until verification. For silent work, pair the verified CLI idle-timeout option with a separate deadline. Keep the original CLI process monitorable; wait for actual computation in the foreground kernel. No dummy keepalive or quota bypass.
8. Write small `progress.json`, logs and a final `result.json` containing job/attempt ID, code/input identity, status and artifact hashes. Finalize local files before durable copying; publish the completion manifest only after outputs are complete. Periodically persist resumable checkpoints; verify a restore. A local file or an asynchronous save request alone is not durable evidence.
9. Accept success only from matching completion evidence and verified artifacts. Exit code 0, local IDLE, notebook history, or a disconnected client alone proves neither success nor remote termination.

## Recover and release

10. On disconnect/timeout/401/404, mark **UNKNOWN**. Preserve the endpoint; do not automatically resubmit, create the same session name, restart or stop. Recheck identity/allocation and fetch small progress/result files with bounded read retries. Do not queue diagnostic execution behind a busy kernel. Resume only after confirming the old attempt stopped, or follow the already agreed cancellation policy. Bound allocation retries too.
11. Persist and verify outputs outside the VM, then stop **only the owned endpoint** and verify release. Release accelerators before CPU-only reporting/postprocessing when required data is durable. Retain a runtime between compatible jobs only when measured restart cost exceeds the bounded idle cost. Never leave UNKNOWN work indefinitely unowned.
12. Report result evidence, location, actual/estimated CU with attribution limits, quality, elapsed time and release status. For UNKNOWN, report the retained endpoint, budget exposure and next decision deadline. Never label unmeasured speedups or illustrative tariffs as observations.

## Load details only when needed

- [Cost, CPU staging, Drive and calculator schema](references/cost-and-staging.md)
- [GPU throughput and numerical correctness](references/gpu.md)
- [TPU shapes, compilation, input pipelines and backends](references/tpu.md)
- [CLI authentication, failure recovery and dated issue evidence](references/operations.md)
- [Dated TPU/framework compatibility](references/compatibility.md)
