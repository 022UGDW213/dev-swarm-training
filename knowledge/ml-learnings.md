# ML Training Learnings

Distilled 2026-09-17 from `odyn-network/lora-hyperparameter-benchmark-v1`
(50 verified configs) and `pgurazada1/machine-failure-mlops-demo-logs` (100).

## LoRA defaults that the corpus supports

- rank 16–32, alpha = rank or 2×rank, dropout 0.05, lr 2e-4, epochs 1–4,
  seq_len 2048–4096, gradient checkpointing on, 4-bit base for QLoRA.
- 2e-4 was the lr in 34/50 configs — it is the default, not 1e-4.
- Effective batch = batch_size × grad_accum; per-device batches of 1–8 are
  normal, don't confuse them with the real batch.
- Dropout 0.0 appears on tiny datasets; 0.05 once you have real data volume.

## What breaks runs

- alpha far from rank (both directions) — keep alpha ∈ {rank, 2×rank}.
- 4096 seq_len without gradient checkpointing on ≤24GB VRAM — OOM.
- Very low lr (5e-6) with short 1–3 epoch schedules — underfits; that lr only
  works with long schedules.
- Library version drift (TRL crashed Juan's Kaggle runs 4×) — pin versions,
  checkpoint adapters every 500 steps.

## MLOps monitoring

- Store features + prediction in the same record (telemetry: temps, rpm,
  torque, tool wear → failure 0/1).
- Alert on input drift, not just prediction flips.
- Retrain triggers must be data-driven, from a labeled eval slice.
