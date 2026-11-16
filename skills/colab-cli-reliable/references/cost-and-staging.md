# Compute-unit budgets, CPU staging and durable storage

Research reviewed: 2026-11-13 (operational updates: 2026-11-16). This is an operating method, not a tariff sheet or a billing guarantee. Check the current CLI and account before execution.

## Contents

- [Optimize the accepted result](#optimize-the-accepted-result)
- [Stage on CPU, then use a new accelerator runtime](#stage-on-cpu-then-use-a-new-accelerator-runtime)
- [Use Drive as durable storage](#use-drive-as-durable-storage)
- [Keep accelerator allocation short](#keep-accelerator-allocation-short)
- [Compare recorded candidates locally](#compare-recorded-candidates-locally)
- [Record a reproducible decision](#record-a-reproducible-decision)

## Optimize the accepted result

Define the same workload, required useful outputs and quality threshold for every candidate. For training, include convergence/validation requirements; equal steps with different learning behavior is not necessarily equal work. For inference, count accepted examples or unpadded tokens, not padded/dropped/duplicate work. A quality failure cannot win on cost.

Estimate a candidate's compute units as:

```text
estimated_CU = sum(rate_CU_per_hour × allocated_seconds / 3600)
CU_per_valid_output = estimated_CU / accepted_output_count
```

Use each runtime's full allocated period, including dependency setup, data transfer, compilation, evaluation, saving and idle gaps. If a rate changes, split that runtime's timeline into nonoverlapping segments. Concurrent runtimes both consume resources: sum their cost, but do not sum their durations to obtain wall time. Track retry/pilot costs separately in the overall project budget even when an unsuccessful candidate is excluded from selection.

This is an estimate from supplied observations. Before/after balance measurements can be confounded by other runtimes, rounding, refills and changing rates. The current `colab usage` display reports **account-wide** balance, hourly consumption and assignment count, not a job-specific invoice. Record the observation time and concurrent assignments; do not stop someone else's runtime to simplify measurement. Prefer isolated observations when available. Do not claim that every second is billed exactly as this model estimates. See [official CLI usage documentation](https://github.com/googlecolab/google-colab-cli/blob/main/docs/04_automation_and_utility.md) and [meter implementation](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/consumption.py).

Set a CU ceiling, wall-clock deadline, small pilot/tuning allowance and response to budget exhaustion before allocating. Monitor at a bounded interval and reserve headroom for saving/release; polling cannot guarantee an exact hard cap. If another allocation is active, report attribution uncertainty. CPU/high-RAM labels are not proof of zero CU: inspect the current rate. Local CPU does not consume Colab units, but its time, electricity and storage can still matter.

**Illustrative arithmetic only, not Colab prices:** a 1 CU/hour candidate taking 2 hours costs 2 CU; a 4 CU/hour candidate taking 15 minutes costs 1 CU. These durations must include all allocated overhead and produce the same acceptable result. Pick the cheapest eligible candidate; report separately if another is fastest.

## Stage on CPU, then use a new accelerator runtime

Hardware switching replaces the runtime. A Colab maintainer explicitly describes tearing down the old VM and creating a new one; current CLI `new` also allocates a new session. The CPU runtime's `/content`, installed packages and Python state are not a handoff mechanism. Sources: [maintainer explanation](https://github.com/googlecolab/colab-vscode/discussions/265), [CLI session implementation](https://github.com/googlecolab/google-colab-cli/blob/v0.8.0/src/colab_cli/commands/session.py).

Use this sequence when preparation would otherwise occupy an expensive accelerator:

1. **Prepare and dry-run bundles locally.** Validate file formats, dimensions, counts, configuration and a small correctness case. Clean/tokenize/resize deterministically, create moderately sized shards, and record code/dependency/input hashes. Keep stochastic augmentation semantics intact. If uploading a minimal source tarball or bundle, **test-extract it into a clean local temporary directory and run `--help`, imports, and any post-training helper/provenance scripts** before allocating a VM so omitted files fail at 0 CU.
2. **Use Colab CPU only when useful.** It can perform preparation or upload to an already authorized durable destination. If the local machine can upload directly to Drive or another suitable store, skip this extra VM and transfer hop.
3. **Make a durable handoff.** Copy code, input shards, prepared features and an input manifest outside the CPU VM. Verify sizes/checksums or trusted object checksums at the destination. A completed local write is insufficient. Record required free disk and restore instructions.
4. **Release the preparation runtime.** Once its outputs are verified, stop that owned allocation and confirm release. Do not overlap CPU and accelerator allocations unless measured time savings justify both costs and fit the budget.
5. **Create the requested GPU/TPU runtime with a unique name.** Do not treat same-name `new` as a hardware upgrade or reconnect. Confirm actual hardware, supported backend and memory before launching a long job.
6. **Restore, preflight assets and run a 1-step check.** Recreate a compatible environment from a manifest; a CPU virtual environment is not automatically portable to GPU/TPU. When staging files with `colab upload`, upload flatly into an existing directory (such as `/content/`) and let the VM setup script place subdirectories (see [CLI operations](operations.md#ファイルとdrive)). Beware **partially preinstalled base-image packages** (for example, a base font/OS package like `fonts-noto-cjk` present without extra variants such as `fonts-noto-cjk-extra`): verify by actually loading every required font, binary, system library and input file rather than checking package names or directories. Run a short **10–20 s preflight** exercising all required assets plus a **minimal 1-step forward/backward and checkpoint save/restore** across every model before full training. Stage active shards onto VM-local storage or stream with bounded prefetch, and reauthorize Drive if the new runtime requires it.

Direct CLI upload to a GPU/TPU VM necessarily happens while it is allocated. A CPU hop helps only if the intermediate data survives outside that VM and the saved accelerator time outweighs additional preparation/transfer costs. For tiny inputs, direct upload after allocation can be cheaper and simpler. A fresh accelerator still incurs unavoidable restore/setup time.

For repeated or multi-stage jobs, reuse immutable preprocessed shards, model weights and compatible dependency downloads. Split sequential multi-stage training so each stage writes an independent verified checkpoint and manifest; if a later stage fails, re-inject already-verified checkpoints onto the fresh VM (via flat `/content/` staging) to skip completed stages without retraining. Keep cache provenance and hashes. Avoid copying arbitrary installed environments or assuming a CPU compilation cache is valid for a TPU. Advanced target-aware CPU compilation is covered in [TPU guidance](tpu.md).

## Use Drive as durable storage

Use Drive for prepared inputs, manifests, checkpoints and final results. Test authorization and a small read/write before the valuable job. Each fresh runtime may require user consent; a mount from the CPU VM does not carry over.

For training on many small files, consolidate them into manageable shards and copy active shards to VM-local disk. Bound the number and size of shards by local disk, host RAM, decompression cost and restart granularity. Do not replace a small-file problem with an archive too large to transfer or unpack. The Colab FAQ describes item-count/I/O failures, mount consent and the benefit of reducing Drive operations; it also warns about interrupted moves. [Official Colab FAQ](https://research.google.com/colaboratory/faq.html)

Use copy → verify → optional cleanup under the agreed retention policy. Never delete the last good source merely because a copy started. Do not assume Drive/FUSE or object storage provides atomic multi-file rename. Finalize a local checkpoint first, copy it into a new immutable generation, verify the copied files, and only then publish its manifest. Treat incomplete generations as uncommitted. Wait for asynchronous saves to finish; see [Orbax checkpointers](https://orbax.readthedocs.io/en/latest/api_reference/checkpoint.checkpointers.html).

Choose checkpoint frequency by the cost of saving versus the amount of work you can afford to repeat. Preserve weights plus optimizer, scheduler, step and any RNG/data-position state needed for the promised resume behavior. A weights-only export is often insufficient for equivalent training continuation. Test restoration before relying on it. [PyTorch checkpoint guidance](https://docs.pytorch.org/tutorials/beginner/saving_loading_models.html) / [TensorFlow checkpoint guidance](https://www.tensorflow.org/guide/checkpoint)

Cloud object storage can suit larger datasets, parallel reads and explicit object manifests. Use an already authorized store and suitable access policy. Storage, requests and network charges are separate from Colab CU; confirm them before introducing a paid service. Do not promise control over consumer Colab placement or free same-region transfers. [Cloud Storage best practices](https://docs.cloud.google.com/storage/docs/best-practices) / [pricing categories](https://cloud.google.com/storage/pricing)

## Keep accelerator allocation short

Order the work: prepare/validate → allocate → restore → asset + 1-step preflight → short pilot → compute → persist/manifest outputs & chunks → verify retrieval outside VM → release → CPU-only export/quantization/parity/tests/reporting. Keep paid GPU/TPU runtimes focused on accelerator computation plus minimal save verification; heavy CPU preprocessing, ONNX/model export, INT8 quantization calibration, strict deployment CPU inference parity checks, full unit test suites, manual inspection and waiting for user input should not keep an accelerator allocated.

Batch compatible experiments into one bounded allocation when common setup/compilation would otherwise repeat. Compare `idle_rate × expected_wait` with the additional restore/setup/compile cost of a fresh runtime; account for uncertain availability and the budget. This is a planning comparison, not a reason to retain a VM indefinitely. Default to release when the next job or wait is unknown.

Fix the measured bottleneck first. A larger accelerator will not repair a stalled Drive read or an authentication prompt. Use short profiling windows; include their cost in the tuning allowance, then benchmark without profiler overhead. Stop tuning when expected remaining-work savings no longer exceed tuning cost.

Emit checkpoints and SHA-256 manifests immediately after training finishes—before optional downstream validation—and always rescue recoverable checkpoints/logs before teardown even when a script exits non-zero or hits a timeout. Release only after required/rescuable artifacts are durable (or according to the agreed cancellation policy). Verify release end-to-end in the ledger: confirm `stop` succeeded on the owned session, verify the owned endpoint is absent in `colab --auth=adc sessions`, and check `colab --auth=adc usage` (expect `0.00/hr` and `0` active assignments when no other owner shares the account; account assignment count need not become zero if other owners have sessions). A disconnect is not a cost-free state. Use the UNKNOWN and cleanup checklists in [CLI operations](operations.md).

## Compare recorded candidates locally

Run the bundled standard-library helper from the skill directory:

```bash
python3 scripts/compare_cu.py --input assets/cost-comparison.example.json --json
python3 scripts/compare_cu.py --input observations.json --max-cus 1.5 --deadline-seconds 1800
```

The included example has **fictional rates and durations**. Replace them with attributed observations. The helper neither queries Colab nor allocates, stops, benchmarks, validates model quality or enforces a live budget.

Top-level JSON keys:

| Key | Meaning |
| --- | --- |
| `workload` | Nonempty workload identifier; use the same code/data scope |
| `quality_target` | Nonempty description of the agreed quality condition |
| `required_valid_outputs` | Positive integer; exact accepted-output count for comparison |
| `candidates` | Nonempty list of recorded alternatives |

Each candidate has a unique `name`, boolean `quality_passed`, nonnegative integer `valid_outputs`, nonnegative finite `elapsed_seconds`, and nonempty `allocation_segments`. Each segment has `runtime_id`, `start_seconds`, `allocated_seconds`, `rate_cu_per_hour`, `rate_source` (`observed` or `illustrative`) and nonempty `rate_evidence`. Times are relative to the candidate start; segments must fit within wall time. Do not overlap segments for one runtime. Separate simultaneously active runtimes use different IDs and their costs sum. Represent genuinely unmetered local-only preparation with an explicit zero-rate segment and explanatory evidence.

Use exact output counts so surplus/padded outputs cannot make an unequal workload win. A candidate with too few **or too many** valid outputs is excluded; normalize or rerun the measurement instead. `quality_passed` is a caller-supplied assertion, not something this script proves. Keep the supporting quality measurements with the observation file.

The helper reports exclusions, estimated CU, CU per accepted output, cheapest eligible candidate and fastest eligible candidate. Exit status is 0 with an eligible result, 1 if none qualifies, and 2 for invalid data. Nonfinite/negative numbers, numeric booleans, invalid timing and overlapping segments are errors. Selection ceilings apply to the supplied estimate, not to a future Colab bill.

## Record a reproducible decision

Keep job/attempt ID, code/data hashes, runtime identity, actual device/topology, framework versions, precision, useful output count, quality evidence, allocation intervals/rates, cold/warm timings, transfers/checkpoint time, total project spend and release evidence. Do not log credentials or authorization URLs. Explain any unmeasured rates, concurrent-use ambiguity, excluded failures and remaining budget.
