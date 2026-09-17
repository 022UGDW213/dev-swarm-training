// dev-swarm-training — zero-dependency Node.js API over the bundled FTS5
// knowledge index (data/index.db) and the skill runbooks (docs/skills/).
// Uses Node's built-in node:sqlite (stable since Node 23.4); no npm deps.

import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url));
const DB_PATH = join(ROOT, 'data', 'index.db');
const SKILLS_DIR = join(ROOT, 'docs', 'skills');

let db = null;
function getDb() {
  if (!db) db = new DatabaseSync(DB_PATH, { readOnly: true });
  return db;
}

/** Escape user text into a safe FTS5 query (implicit AND of quoted tokens). */
function toFtsQuery(q) {
  const tokens = String(q)
    .split(/\s+/)
    .map((t) => t.replace(/"/g, '""').trim())
    .filter(Boolean);
  if (!tokens.length) throw new Error('empty query');
  return tokens.map((t) => `"${t}"`).join(' ');
}

const LANES = ['ml-training', 'llm-ops', 'swarm-multiagent', 'mcp-protocol'];

/**
 * Full-text search the knowledge index.
 * @param {string} query  keywords, e.g. "LoRA rank alpha"
 * @param {{lane?: string, limit?: number}} [opts]  lane filters to one of the
 *   four training lanes; limit defaults to 5.
 * @returns {Array<{lane, dataset, text, rank}>} best matches first.
 */
export function searchKnowledge(query, { lane = null, limit = 5 } = {}) {
  if (lane && !LANES.includes(lane)) {
    throw new Error(`unknown lane "${lane}" — expected one of: ${LANES.join(', ')}`);
  }
  const match = toFtsQuery(query);
  const sql = lane
    ? `SELECT agent_id AS lane, dataset, text, rank
       FROM docs WHERE docs MATCH ? AND agent_id = ?
       ORDER BY rank LIMIT ?`
    : `SELECT agent_id AS lane, dataset, text, rank
       FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?`;
  const params = lane ? [match, lane, limit] : [match, limit];
  return getDb().prepare(sql).all(...params);
}

/**
 * Doc counts per lane (and total) from the index.
 * @returns {{total: number, lanes: Record<string, number>}}
 */
export function stats() {
  // FTS5 supports full-table scans with GROUP BY.
  const rows = getDb()
    .prepare('SELECT agent_id, COUNT(*) AS n FROM docs GROUP BY agent_id')
    .all();
  const lanes = Object.fromEntries(rows.map((r) => [r.agent_id, r.n]));
  const total = Object.values(lanes).reduce((a, b) => a + b, 0);
  return { total, lanes };
}

/** Names of the bundled skill runbooks, e.g. ["llm-ops", ...]. */
export function listSkills() {
  return readdirSync(SKILLS_DIR)
    .filter((f) => f.endsWith('.md'))
    .map((f) => f.slice(0, -3))
    .sort();
}

/**
 * Read a bundled skill runbook as Markdown.
 * @param {string} name  e.g. "mcp-protocol"
 */
export function getSkill(name) {
  const safe = String(name).replace(/[^a-z0-9-]/gi, '');
  const path = join(SKILLS_DIR, `${safe}.md`);
  try {
    return readFileSync(path, 'utf8');
  } catch {
    throw new Error(`unknown skill "${name}" — available: ${listSkills().join(', ')}`);
  }
}

/** Close the underlying database handle (optional; the module manages it). */
export function close() {
  if (db) {
    db.close();
    db = null;
  }
}
