# Reliable Google Colab CLI skills

[日本語](README.ja.md) · [Agent skill](skills/colab-cli-reliable/SKILL.md) · [MIT license](LICENSE)

An open-source agent skill for reliable, economical use of the **official Google Colab CLI**. It covers CPU preparation, GPU/TPU execution, Google Drive, disconnections, checkpoints and resource release.

**Goal: minimize total Colab compute units to a verified result at the required quality and deadline.** CU and CCU both refer to Colab compute units in this project. This is an independent community project, not an official Google skill or a replacement CLI.

- Skill created: **2026-11-13T09:25:10Z** / **2026-11-13 18:25:10 JST** (initial saved version).
- Research reviewed: **2026-11-13**.
- Main instructions are short; framework details and volatile compatibility findings are loaded as references.
- No Colab runtime was allocated and no compute units were spent to produce this research or run the local validation.

## The important CPU-to-GPU/TPU distinction

Preparing/uploading on CPU can reduce accelerator allocation time, but changing hardware creates a **new runtime**. The old VM's `/content`, packages and kernel state do not transfer. [Colab maintainer explanation](https://github.com/googlecolab/colab-vscode/discussions/265)

Use this sequence:

1. Prepare and validate locally, or use a CPU runtime when helpful.
2. Upload/copy inputs and a checksum manifest to durable storage such as Drive; verify the handoff.
3. Release the CPU runtime once its outputs are durable.
4. Allocate the intended GPU/TPU, verify the actual backend/device, and restore only the required data.
5. Compute, persist and verify results, release the accelerator, then finish CPU-only reporting.

If local upload directly to durable storage works, skip an unnecessary CPU VM. Do not assume Colab CPU/high-RAM is free. Include the extra staging/restore cost: tiny jobs may be better served by direct upload after allocation. [Detailed staging and cost guidance](skills/colab-cli-reliable/references/cost-and-staging.md)

## What the skill teaches an agent

| Area | Operating rule |
| --- | --- |
| Cost | Compare complete allocation cost at equal useful work and quality; measure current rates |
| CPU/Drive | Prepare early, persist across runtime changes, stage active shards locally |
| GPU | Tune input supply, batch and precision; avoid host synchronization; amortize compilation |
| TPU | Verify actual topology/backend, stabilize shapes, bound padding and verify cache hits |
| Reliability | Treat a disconnect as UNKNOWN; do not duplicate work or destroy an unverified result |
| Evidence | Use job/attempt IDs, progress/result manifests, artifact hashes and resumable checkpoints |
| Release | Stop only the owned endpoint after durable verification or the agreed cancellation policy |

The design does not hard-code hourly tariffs, an “always fastest” accelerator, TPU device counts or future PR commands. PyTorch TPU backend changes and version-specific CLI failures live in dated reference notes.

## Use with an agent

```bash
git clone https://github.com/Aero123421/use-google-colab-cli-skills.git
```

Point a skill-capable agent at [skills/colab-cli-reliable/SKILL.md](skills/colab-cli-reliable/SKILL.md), or copy the **entire** `colab-cli-reliable` folder into your agent's documented project/user skill location. Keep its references, script and example together. The Colab CLI and account authorization are separate prerequisites; use the dated operations notes and current installed help.

Example request:

> Use colab-cli-reliable to prepare this workload on CPU, compare authorized GPU/TPU options within my CU and time budget, preserve the required quality, recover safely from disconnections, verify durable results and release my runtime.

## Local CU comparison helper

This standard-library script compares **supplied observations**. It does not connect to Colab, allocate resources, verify quality, discover tariffs or enforce a live spending cap.

```bash
python3 skills/colab-cli-reliable/scripts/compare_ccu.py \
  --input skills/colab-cli-reliable/assets/cost-comparison.example.json \
  --max-cus 0.7 --deadline-seconds 1800 --json
```

**All shipped example rates and timings are fictional.** Replace them with attributed measurements before making a real choice. The helper sums allocation segments, including simultaneous distinct runtimes, and excludes quality failures, unequal output counts and candidates exceeding the supplied limits. It reports both the cheapest and fastest eligible options. [Schema and interpretation](skills/colab-cli-reliable/references/cost-and-staging.md#compare-recorded-candidates-locally)

## Contents and evidence

| File | Purpose |
| --- | --- |
| [SKILL.md](skills/colab-cli-reliable/SKILL.md) | Compact, durable agent instructions |
| [Cost and staging](skills/colab-cli-reliable/references/cost-and-staging.md) | Budgets, CPU handoff, Drive, checkpoints, calculator schema |
| [GPU](skills/colab-cli-reliable/references/gpu.md) | Throughput, numerical checks and compilation tradeoffs |
| [TPU](skills/colab-cli-reliable/references/tpu.md) | Topology, shapes, input pipelines, timing and optional CPU cross-compilation |
| [CLI operations](skills/colab-cli-reliable/references/operations.md) | Dated CLI/authentication/disconnection investigation, in Japanese |
| [Compatibility](skills/colab-cli-reliable/references/compatibility.md) | Dated CLI/framework support and migration notes |
| [Tests](tests/test_compare_ccu.py) | Offline arithmetic, comparison gates and invalid-input checks |

Technical recommendations cite official Colab, Google Cloud, JAX, PyTorch and TensorFlow sources. Firsthand issues and community posts are labeled observations; they do not establish failure rates or guaranteed prices. Source research and local helper validation do not substitute for an authorized, representative test on the user's actual runtime.

## Development

Run the offline helper checks without creating bytecode files:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Keep the main skill brief, put changing facts in dated references, and cite primary sources. Preserve the creation timestamp. See [AGENTS.md](AGENTS.md) for maintenance rules.

## License

[MIT](LICENSE), copyright 2026 Aero123421. Referenced upstream projects and documentation retain their respective licenses. This repository does not bundle the Google Colab CLI implementation.
