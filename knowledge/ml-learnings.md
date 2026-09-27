# ML Training Learnings

Distilled 2026-09-17 from `odyn-network/lora-hyperparameter-benchmark-v1`
(50 verified configs) and `pgurazada1/machine-failure-mlops-demo-logs` (100).

## LoRA defaults that the corpus supports

- rank concentrates at 8/16/32 (32 in 20/50, 8 in 10/50, 16 in 6/50 = 36 of the
  50 configs); the remaining 14 scatter from 2 up to 256. Defaults: dropout
  0.05, lr 2e-4, epochs 1–4 (a 1-epoch run is the single most common, 18/50),
  seq_len 2048–4096, gradient checkpointing on (31 of the 34 configs that
  report it), 4-bit base for QLoRA.
- alpha is 16 or 32 in 35/50 configs (16 in 27/50, 32 in 8/50). The literal
  equivalences hold less often than the "alpha = rank or 2×rank" rule suggests —
  `alpha == rank` in 7/50 and `alpha == 2×rank` in 19/50 — with the remaining
  21 configs off both relations and 3 not reporting alpha at all.
  Verify:
  `sqlite3 data/index.db "select text from docs where dataset='odyn-network/lora-hyperparameter-benchmark-v1'" | grep -cE 'lora_alpha_effective=(16|32),'` → `35`.
- 2e-4 was the lr in 34/50 configs — it is the default, not 1e-4.
- Effective batch = batch_size × grad_accum; per-device batches of 1–8 cover
  40/50 configs, don't confuse them with the real batch.
- Dropout 0.0 appears on tiny datasets; 0.05 once you have real data volume.

## What breaks runs

- alpha far from rank (both directions) — keep alpha ∈ {rank, 2×rank}.
- 4096 seq_len without gradient checkpointing on ≤24GB VRAM — OOM.
- Very low lr underfits short runs: 5e-6–1e-5 appears in only 3/50 configs;
  2e-4 is the proven default for 1–3 epoch SFT.
  (Verify: `sqlite3 data/index.db "select text from docs where dataset='odyn-network/lora-hyperparameter-benchmark-v1'" | grep -cE 'learning_rate=(5e-06|1e-05)'` → `3`.)
- Library version drift (a TRL bump changing trainer defaults mid-run) — pin
  versions and checkpoint adapters every 500 steps rather than trusting a long
  run to complete.

## MLOps monitoring

- Store features + prediction in the same record (telemetry: temps, rpm,
  torque, tool wear → failure 0/1).
- Alert on input drift, not just prediction flips.
- Retrain triggers must be data-driven, from a labeled eval slice.
