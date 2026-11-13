# Dated compatibility notes

**Checked: 2026-11-13.** These are source-based observations, not a live Colab GPU/TPU acceptance test. Recheck before changing a working environment. Keep versions, current flags, available hardware and announced future changes out of the evergreen rules.

## Official Colab CLI

The researched distribution is `google-colab-cli` **0.8.0**, Python **3.12+**, with Linux/macOS listed as supported platforms. Use `colab version`, the actual subcommand help and the installed distribution as the execution contract. README, main branch, a proposed PR and a released wheel can differ. Do not upgrade a running job. [PyPI](https://pypi.org/project/google-colab-cli/0.8.0/) / [official repository](https://github.com/googlecolab/google-colab-cli)

Read [CLI operations](operations.md) for the dated authentication/timeout/recovery evidence. It records the ADC selection, OAuth fix not yet present in the researched release, WebSocket result-recovery issue, exit-code pitfalls, full-file transfer limitations and bounded recovery procedure. Those checks must be revisited when a new release is adopted.

## PyTorch on TPU is changing

Google's current recommendation for new PyTorch TPU work is **TorchTPU**. The official PyTorch platform page lists a Google Colab TPU runtime as a supported hardware environment. This establishes documented support, not that every preinstalled Colab image/version combination has been tested here. Check the actual allocation and perform a small device/quality test. [Google TPU/PyTorch guide](https://docs.cloud.google.com/tpu/docs/pytorch-on-tpu) / [PyTorch platforms](https://docs.pytorch.org/get-started/additional-platforms/)

The PyTorch/XLA master documentation currently marks that project deprecated and announces repository archival for **2026-11-15**. On this note's November 13 review date, that is a future plan; do not report the repository as already archived. Existing working workloads need a tested migration plan rather than an in-job package replacement. [PyTorch/XLA notice](https://docs.pytorch.org/xla/master/perf/recompilation.html)

Current TorchTPU documentation uses the native `"tpu"` device and `torch.compile(..., backend="tpu")`. Do not mix these instructions with old `torch_xla`-specific calls. It currently describes bounded dynamic shapes, with `dynamic=True` unsupported, possible recompilation when bounds/layouts change, and no persistent `AOTAutogradCache` reuse for bounded-dynamic executables. These limitations may change; recheck the specific installed version. [Execution model](https://torchtpu.readthedocs.io/en/latest/torchtpu_execution_model/) / [dynamic shapes](https://torchtpu.readthedocs.io/en/latest/dynamic_shapes/)

Internal float32 matrix arithmetic and precision controls can differ from CUDA. Match explicit precision settings and task-level tolerances when comparing backends. [TorchTPU numerical precision](https://torchtpu.readthedocs.io/en/latest/numerical_precision/)

## Generation and framework support

Verify the framework support matrix for the **actual TPU generation and software image**, not merely the presence of a TPU selector. JAX, TensorFlow and PyTorch examples from different TPU generations are not interchangeable. TensorFlow data-pipeline guidance does not establish that TensorFlow execution is supported on the chosen TPU.

The current Cloud TPU software table lists TensorFlow **2.15+ on v5e/v5p/v6e using PJRT**, with API/feature differences from older generations; it explicitly excludes TensorFlow on **TPU7x**. This is a Cloud TPU compatibility table, not verification of a particular Colab image or a promise that consumer Colab exposes Cloud TPU VM image-selection flags. Do not assume either universal TensorFlow support or universal non-support on newer TPUs. [Cloud TPU versions and software](https://docs.cloud.google.com/tpu/docs/runtimes)

## Recheck at upgrade time

- Confirm the package release and installed executable agree; review relevant merged changes rather than open PR examples.
- Revalidate authentication refresh, silent execution, failure/completion evidence, a checkpoint restore and release on the smallest authorized runtime.
- Verify actual device placement, framework/driver/runtime compatibility, a tiny numerical baseline, topology and any compile-cache hit.
- Re-measure the current account consumption rate and whole-job cost. Keep example rates explicitly fictional.
- Record review date, version and observed limitations. Never convert an announcement, issue hypothesis or community benchmark into a universal guarantee.
