# ML Training Skill

Runbook for fine-tuning and MLOps work. Grounded in 150 HF docs:
`odyn-network/lora-hyperparameter-benchmark-v1` (50 verified LoRA configs) +
`pgurazada1/machine-failure-mlops-demo-logs` (100 monitoring records).

## LoRA / QLoRA recipe (what the benchmark corpus actually uses)

Distributions from 50 verified configs — use these as your defaults:

| Hyperparam | Common values | Default pick |
|---|---|---|
| `lora_rank` | 8–32 (32 in 20/50; 8 in 10/50; 16 in 6/50) | **16 or 32** |
| `lora_alpha` | 16 (27/50), 32 (8/50); 64–512 in the rest | **16, or 32 with rank 32** |
| `lora_dropout` | 0.05 (27/50), 0.0 (10/50) | **0.05** |
| `learning_rate` | 2e-4 (34/50), 1e-4 (9/50) | **2e-4** |
| `num_epochs` | 1–4 common (1 in 18/50, 2 in 11/50, 4 in 10/50, 3 in 7/50) | **1–3** |
| `seq_len` | 2048 (18), 4096 (12) | **4096** if VRAM allows |
| `gradient_checkpointing` | on in 31/34 reporting configs | **on** |
| `base_precision` | full bf16 (22), 4-bit (20) | **4-bit QLoRA** on consumer GPUs |

Effective batch = `batch_size × grad_accum` — corpus runs tiny per-device
batches (1–8) with grad accumulation; don't mistake per-device batch for the
real one. ~50k samples with rank 16 / alpha 32 / lr 2e-4 / 1 epoch is a proven
working point (ax-llama3.2-1b-lora).

## Quick config template (Unsloth/TRL style)

```python
r, lora_alpha, lora_dropout = 16, 32, 0.05
lr, epochs = 2e-4, 3
max_seq_length = 4096
use_gradient_checkpointing = True
load_in_4bit = True          # QLoRA on limited VRAM
```

## Pitfalls

- **Alpha/rank mismatch:** alpha ≪ rank starves the adapter; alpha ≫ 4×rank
  destabilizes. Corpus sweet spot: alpha ∈ {rank, 2×rank}.
- **lr too low on short runs:** 5e-6–1e-5 appears in only 4/50 configs;
  for 1–3 epoch SFT runs, 2e-4 is the proven default.
- **No dropout on tiny data:** with <1k samples some configs use dropout 0.0 —
  with ≥10k samples, 0.05 is safer.
- **Forgetting checkpointing:** without it, seq_len 4096 on 8–24GB VRAM OOMs.
  The corpus has it on in nearly every reporting config.
- **Library version drift:** a TRL bump can change trainer defaults mid-run —
  pin the TRL version, save adapter checkpoints every 500 steps, and don't
  rely on a long run completing untouched.

## MLOps monitoring (from the failure-prediction demo logs)

Production failure classification on machine telemetry: air temp, process temp,
rotational speed (rpm), torque (Nm), tool wear (min), machine type → binary
failure prediction. Takeaways for any monitoring setup:

- Log **features and predictions together** (the demo rows carry the model
  output in the same record) so drift/degradation is auditable.
- Alert on **input distribution shift** (rpm/torque drift), not just on
  prediction flips — models go stale silently.
- Keep a labeled evaluation slice; retrain triggers should be data-driven.
