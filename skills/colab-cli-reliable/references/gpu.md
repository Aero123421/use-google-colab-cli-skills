# GPU work per compute unit

Research reviewed: 2026-11-13. Apply only settings supported by the actual runtime, framework and model. No GPU model is universally cheapest.

## Measure before changing settings

Run a short representative pilot with the real input shapes and a defined quality threshold. Measure complete allocation cost and cold-start time separately from warmed throughput. Sample preprocessing, input waits, transfers, kernels, memory and checkpointing with a short profiler window. Remove profiling overhead for the final comparison. [PyTorch profiler](https://docs.pytorch.org/docs/main/profiler)

Accelerator execution is asynchronous. Use CUDA events or explicit synchronization at measurement boundaries; timing a Python call's return may omit device work. Avoid synchronizing every production step just to measure it. Record warm-up updates/data consumption if they change training state. [CUDA semantics](https://docs.pytorch.org/docs/main/notes/cuda.html)

## Prioritize the actual bottleneck

| Observed bottleneck | Candidate change | Condition to verify |
| --- | --- | --- |
| CPU preprocessing or input wait | Preprocess/cache reusable work; tune workers, batched transforms and prefetch | Host RAM, shared memory, deterministic/random augmentation semantics |
| Host-to-device copies | DataLoader pinned memory; supported asynchronous transfers; enough work to overlap | Pinned-memory budget, correct streams/lifetimes, actual overlap |
| Many small kernels or host gaps | Larger useful batches, supported fusion/compilation, less frequent host metrics | Quality, memory headroom, compilation amortization |
| Memory limit | Mixed precision, suitable physical batch, accumulation or activation recomputation | Numerical checks and full completion time |
| Recompilation | Stable shapes, bounded length buckets, compatible persistent caches | Padding overhead and observed cache hits |
| Durable I/O | Local working set, sharded writes, less frequent recovery checkpoints | Restoreability and acceptable replay window |

Tune one meaningful change at a time, retain the baseline and cap tuning CU. High utilization alone is not proof of useful work or low cost.

## Batch, precision and inference

Increase the physical batch only while useful throughput improves and memory retains headroom. Preserve the intended effective batch and optimization behavior. Gradient accumulation can fit the target effective batch into memory, but extra microsteps can be slower; keep loss scaling, optimizer/scheduler steps and clipping correctly aligned. [AMP accumulation examples](https://docs.pytorch.org/docs/main/notes/amp_examples.html)

Try supported BF16/FP16 autocast with a numerical baseline; check finite loss, gradients and required validation/inference quality. Use the framework's appropriate scaling rules rather than converting every tensor with `.half()`. BF16 and FP16 do not have identical range or loss-scaling requirements. Verify the device supports the desired mode. [PyTorch AMP](https://docs.pytorch.org/docs/main/amp.html)

For inference, set model evaluation behavior and disable unnecessary autograd bookkeeping where applicable. `model.eval()` and `torch.inference_mode()` solve different problems; neither should be assumed to imply the other. Keep gradients enabled for tasks that actually need them. [Inference mode](https://docs.pytorch.org/docs/stable/generated/torch.autograd.grad_mode.inference_mode.html)

Consider supported fused/foreach optimizers or model-specific fused attention only after correctness/memory checks. TF32, channels-last and convolution autotuning depend on workload, hardware, numerical tolerance and shape stability; they are candidates, not universal flags. [Performance guide](https://docs.pytorch.org/tutorials/recipes/recipes/tuning_guide) / [AdamW options](https://docs.pytorch.org/docs/main/generated/torch.optim.AdamW.html)

## Feed the device without accidental synchronization

Tune DataLoader workers against measured input wait rather than choosing every CPU core. Worker processes and prefetch queues consume RAM; iterable datasets need correct worker/rank sharding to avoid duplicated examples. [DataLoader documentation](https://docs.pytorch.org/docs/main/utils/data.html)

Pinned memory and `non_blocking=True` do not guarantee overlap. Manually pinning each batch on the main thread can add overhead. Check the transfer mechanism and buffer ownership; do not modify a host buffer before its asynchronous upload completes or read an unfinished device-to-host result. [Pinned-memory and nonblocking-transfer tutorial](https://docs.pytorch.org/tutorials/intermediate/pinmem_nonblock.html)

Reduce `.item()`, CPU/NumPy conversion, tensor printing and host-side tensor branches inside hot loops. Aggregate metrics and read them periodically while keeping enough progress reporting for recovery. Avoid transferring unchanged tensors repeatedly. [CUDA semantics](https://docs.pytorch.org/docs/main/notes/cuda.html)

## Pay back compilation and memory tradeoffs

Compare eager and compiled runs including cold compilation and any recompilations. A useful planning test is:

```text
remaining_steps × (eager_step_seconds - compiled_step_seconds)
    > initial_compile_seconds + expected_recompile_seconds
```

This estimate assumes equivalent quality and comparable steady-state measurements; include deployment/setup cost too. Do not spend most of a short job compiling or autotuning it. Reuse stable graphs and supported caches with matching environment/shape/precision, and verify hits rather than merely creating a cache directory. [Reducing compile time](https://docs.pytorch.org/docs/main/user_guide/torch_compiler/compile/programming_model.reducing_compile_time.html)

**Activation checkpointing** recomputes activations to save memory; it is distinct from a **recovery checkpoint** saved outside the VM. Recomputation may lower total CU if it enables a faster feasible batch or cheaper device, but it can also slow execution. Compare the full job. [Activation checkpointing tradeoffs](https://pytorch.org/blog/activation-checkpointing-techniques/)

Do not call `empty_cache()` every batch as a generic speed optimization: it releases unused allocator cache, not live model tensors, and can add allocation work. Diagnose memory growth and fragmentation first. [CUDA memory management](https://docs.pytorch.org/docs/main/notes/cuda.html)

## Stop at a verified result

Use the same useful outputs and quality threshold for every comparison. Count tuning, failed attempts, evaluation and export in the overall budget. Persist the required result and resumable state, verify the copies, release the owned accelerator, then finish CPU-only plots or reporting. See [cost and staging](cost-and-staging.md).
