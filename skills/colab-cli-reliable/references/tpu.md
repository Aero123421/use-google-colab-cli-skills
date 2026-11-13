# TPU work per compute unit

Research reviewed: 2026-11-13. Keep these operating principles separate from the changing backend/version details in [compatibility](compatibility.md).

## Contents

- [Confirm suitability and actual devices](#confirm-suitability-and-actual-devices)
- [Stabilize shapes and compilation](#stabilize-shapes-and-compilation)
- [Choose precision and useful batch size](#choose-precision-and-useful-batch-size)
- [Feed the TPU and limit host round trips](#feed-the-tpu-and-limit-host-round-trips)
- [Measure real completion](#measure-real-completion)
- [Distribute only when justified](#distribute-only-when-justified)
- [Advanced CPU-side compilation](#advanced-cpu-side-compilation)
- [Finish with a restorable checkpoint](#finish-with-a-restorable-checkpoint)

## Confirm suitability and actual devices

TPUs are candidates for sufficiently large, regular tensor workloads. Small one-off tasks, input-bound jobs, frequent host decisions, unsupported custom operations or stringent numerical requirements can favor CPU/GPU after overhead is counted. Make a short representative comparison at the same output quality. [Google TPU introduction](https://docs.cloud.google.com/tpu/docs/intro-to-tpu) / [JAX benchmarking](https://docs.jax.dev/en/latest/benchmarking.html)

Check the actual TPU generation, backend/library compatibility, available memory, device count, local-device count and process count. Never hard-code “TPU means eight cores.” A historical v2-8/v3-8 performance example is not a topology contract for every Colab TPU. Confirm a tiny operation executes on the requested device; CPU correctness alone is not target-device compatibility. [Google performance guide](https://docs.cloud.google.com/tpu/docs/performance-guide)

For a **single-process JAX** runtime, inspect explicitly:

```python
import jax

devices = jax.devices("tpu")
print({
    "jax": jax.__version__,
    "devices": [str(device) for device in devices],
    "device_count": jax.device_count("tpu"),
    "local_device_count": jax.local_device_count("tpu"),
    "process_count": jax.process_count(),
})
```

An unavailable TPU backend should fail instead of silently choosing CPU. In a distributed configuration, perform the framework's required distributed initialization **before** querying/initializing the backend. Device count is not interchangeable with host count or physical chip count. [JAX API](https://docs.jax.dev/en/latest/jax.html) / [distributed initialization](https://docs.jax.dev/en/latest/_autosummary/jax.distributed.initialize.html)

## Stabilize shapes and compilation

- Keep shapes, dtypes and relevant control flow stable. Bucket variable-length inputs into a small set of useful sizes. Measure padding work: padding everything to the largest sequence can erase the gain.
- Preserve all required evaluation/inference examples. Drop a remainder only when the training contract allows it; otherwise pad and mask correctly or use supported variable-shape handling.
- Define compiled/JIT functions outside the hot loop. Avoid repeatedly creating temporary lambdas/functions or changing static arguments without need.
- Reuse a supported persistent compilation cache only with compatible versions, compiler flags, topology, shapes and sharding. Verify actual cache hits; a populated directory is not proof of reuse. Keep executable caches trusted and restrict writers.

Sources: [JAX JIT](https://docs.jax.dev/en/latest/jit-compilation.html), [JAX persistent cache and key](https://docs.jax.dev/en/latest/persistent_compilation_cache.html), [TF dataset batching/bucketing](https://www.tensorflow.org/api_docs/python/tf/data/Dataset). The TF data concepts are useful independently of whether the allocated TPU supports TensorFlow execution.

## Choose precision and useful batch size

Try supported BF16/mixed precision against a numerical baseline, retaining suitable precision for sensitive acumulations, reductions or optimizer state. Compare finite values, convergence and task-level quality. BF16 and FP16 do not share the same dynamic range/loss-scaling assumptions. A float32 storage dtype also does not guarantee identical internal matrix arithmetic across backends. [Google BF16](https://docs.cloud.google.com/tpu/docs/bfloat16) / [TensorFlow mixed precision](https://www.tensorflow.org/guide/mixed_precision) / [TorchTPU numerical precision](https://torchtpu.readthedocs.io/en/latest/numerical_precision/)

Choose the per-device batch and matrix dimensions using actual device count, tiling behavior and memory headroom. Favor useful large tensor work without fixing a universal multiple or blindly filling all HBM. Check the effective batch, learning schedule, required updates and latency constraints. Internal padding and sharding can leave a nominally large global batch small on each device. [Google performance guide](https://docs.cloud.google.com/tpu/docs/performance-guide)

Activation recomputation trades extra calculation for memory. Use it when the resulting feasible configuration improves the complete workload's CU; distinguish it from durable recovery checkpoints. Compare the measured result rather than assuming either a larger batch or fewer bytes always saves cost.

## Feed the TPU and limit host round trips

Preprocess reusable work on CPU, then supply local/streamed shards with parallel reads, batched transforms and bounded prefetch. Verify CPU and I/O can keep up. Bound host RAM use; caching after random augmentation can accidentally freeze augmentation. TensorFlow's `tf.data` guide explains the general pipeline tradeoffs. [Input pipeline performance](https://www.tensorflow.org/guide/data_performance)

Avoid per-step tensor printing, NumPy conversion, `.item()`/`.cpu()` and host-side decisions that require device values. Acumulate metrics on device and retrieve them periodically. Preserve small progress updates at an interval compatible with the deadline/recovery policy. [JAX asynchronous dispatch](https://docs.jax.dev/en/latest/async_dispatch.html)

Where supported, execute several small steps per compiled call to reduce Python overhead. Limit grouping so cancellation, callbacks and progress do not become unresponsive. TensorFlow's `steps_per_execution` is one framework-specific example, usable only on a compatible runtime. [TensorFlow TPU guide](https://www.tensorflow.org/guide/tpu)

## Measure real completion

Separate data placement, initial compilation/first execution, steady execution, evaluation and durable saving. Synchronize asynchronous results at measurement boundaries. For a repeatable side-effect-free JAX function:

```python
import time
import jax

compiled_fn = jax.jit(fn)
started = time.perf_counter()
out = compiled_fn(x)
jax.block_until_ready(out)
cold_seconds = time.perf_counter() - started

started = time.perf_counter()
out = compiled_fn(x)
jax.block_until_ready(out)
warm_seconds = time.perf_counter() - started
```

`fn` and `x` are workload-supplied placeholders. Put device transfer inside or outside these intervals deliberately and account for it either way. Warm-up of a training step consumes data, RNG and updates weights; record or restore that state instead of treating it as free. Do not insert synchronization into every production step. [JAX benchmarking](https://docs.jax.dev/en/latest/benchmarking.html)

Profile briefly to separate input waits, compilation, device computation, memory and communication. Only then try a different backend, batch, sharding or accelerator. Include profiling/tuning in the budget and stop when its expected payback exceeds the remaining workload.

## Distribute only when justified

Use the actual supported topology and initialization sequence. Shard examples correctly across workers, align step counts and collective operations, and avoid rank-specific control flow that causes other ranks to wait forever. Do not launch a historical eight-process example on a single-device allocation. Extra processes and communication can cost more than they save on small jobs. [JAX distributed initialization](https://docs.jax.dev/en/latest/_autosummary/jax.distributed.initialize.html) / [TorchTPU distributed support](https://torchtpu.readthedocs.io/en/latest/distributed_support/)

## Advanced CPU-side compilation

Ordinary CPU JIT output is not a TPU executable. However, JAX documents **target-aware cross-compilation on a CPU host using a virtual TPU topology**, followed by reuse through a persistent cache. This can move compilation away from paid accelerator allocation for known, repeated workloads. It is an advanced optional path, not the default staging method. [JAX cross-compilation](https://docs.jax.dev/en/latest/aot.html#cross-compiling-for-cloud-tpu-via-the-compilation-cache)

Follow the current procedure exactly: match Python/library/compiler versions, pre-import flags, target topology, mesh and input sharding. Cache misses can silently trigger TPU compilation. Verify a real hit on the allocated target and include CPU preparation/storage/transfer costs. Do not claim a saving from cache existence alone. Do not add cloud storage billing merely because an example uses a `gs://` URI; use an appropriate authorized handoff.

## Finish with a restorable checkpoint

Persist model and resume state outside the VM at a frequency balancing save overhead against acceptable replay. Record step, code/data identity and the last verified checkpoint. Wait for asynchronous writes and validate the destination before calling the job complete. Then release the owned TPU and finish CPU-only work elsewhere. See [cost and staging](cost-and-staging.md) and [CLI recovery](operations.md).
