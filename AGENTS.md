# Maintaining this repository

- Keep `skills/colab-cli-reliable/SKILL.md` short and procedural. Put framework-specific details in directly linked references.
- Preserve the original creation timestamp. Date every compatibility/research snapshot and recheck changing claims before updating it.
- Support technical claims with primary sources. Distinguish released behavior, main-branch changes, proposed PRs and firsthand issue reports.
- Optimize total compute units to equal useful work at the required quality. Never publish illustrative rates, untested speedups or an account-wide usage delta as a measured per-job tariff.
- Preserve the CPU → verified durable handoff → new accelerator lifecycle. Do not imply `/content` or an installed environment survives a hardware change.
- Preserve UNKNOWN recovery, single-owner mutation and the previously agreed budget/cancellation policy. Never add blind retries or same-name session replacement.
- Keep GPU/TPU device counts, prices and version-specific backend APIs out of evergreen rules. Check actual device placement and compatibility.
- Never add credentials, session metadata, tokens, authorization URLs, private data or executable compile caches to this repository.
- Use only offline checks by default. Do not authenticate to Colab, provision a runtime, spend CU, enable cloud billing or run paid benchmarks as part of documentation/CI validation.
- Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` after changing the CU helper. Cover meaningful arithmetic and selection risks, not prose formatting.
- Keep README English/Japanese behavior descriptions aligned. The CLI investigation reference is currently Japanese; preserve its evidence and conditions when translating.
- Include the complete skill folder when distributing. This project is MIT; respect the licenses of referenced upstream material and do not copy their implementation into the project without handling attribution/license obligations.
