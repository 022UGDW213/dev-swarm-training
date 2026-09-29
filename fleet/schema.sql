-- Fleet training dataset base: query tunnel index.
-- One FTS5 table; every row carries the agent it trains and the source dataset.
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS sources (
  agent_id   TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  license    TEXT,
  rows_total INTEGER,
  rows_used  INTEGER,
  columns    TEXT,
  ingested_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(
  agent_id,
  dataset_id,
  title,
  body,
  tags,
  tokenize = 'porter'
);
