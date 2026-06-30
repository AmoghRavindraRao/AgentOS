-- AgentOS app SQLite schema (Day 1).
-- Cognee owns the graph, vectors, and session memory. These tables hold only
-- thin coordination state that maps app concepts onto Cognee dataset names.

-- domains: app-level brain namespaces
CREATE TABLE IF NOT EXISTS domains (
    id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    "user"       TEXT NOT NULL,
    slug         TEXT NOT NULL,
    title        TEXT NOT NULL,
    -- Cognee dataset_name: "u_{safe(user)}_d_{safe(slug)}" — unique and immutable
    dataset_name TEXT NOT NULL UNIQUE,
    created_at   REAL DEFAULT (unixepoch('now')),
    UNIQUE("user", slug)
);

-- sessions: one row per agent run
CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    domain_id    TEXT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    query        TEXT NOT NULL,
    -- status in {planning, researching, writing, improving, complete, error}
    status       TEXT DEFAULT 'planning',
    output       TEXT,
    created_at   REAL DEFAULT (unixepoch('now')),
    completed_at REAL
);

-- sources: documents ingested into a domain
CREATE TABLE IF NOT EXISTS sources (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    domain_id       TEXT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    -- cognee_data_id: result.items[0]["id"] from remember() — handle for forget(data_id=...)
    -- NULL while indexing; non-NULL = eligible for forget_source()
    cognee_data_id  TEXT,
    kind            TEXT NOT NULL,   -- web | url | pdf | text
    uri             TEXT NOT NULL,
    title           TEXT,
    added_at        REAL DEFAULT (unixepoch('now'))
);

-- confidence: re-ranker state — never written by Cognee, only by our app
CREATE TABLE IF NOT EXISTS confidence (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    domain_id   TEXT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    -- node_ref: source data_id from recall() result (stable handle, read-only from Cognee)
    node_ref    TEXT NOT NULL,
    score       REAL DEFAULT 0.5,    -- score in [0.0, 1.0]
    upvotes     INTEGER DEFAULT 0,
    last_seen   REAL DEFAULT (unixepoch('now')),
    forgotten   INTEGER DEFAULT 0,   -- 1 = filtered from all future recall results
    UNIQUE(domain_id, node_ref)
);

CREATE INDEX IF NOT EXISTS idx_sessions_domain  ON sessions(domain_id);
CREATE INDEX IF NOT EXISTS idx_sources_domain   ON sources(domain_id);
CREATE INDEX IF NOT EXISTS idx_confidence_score ON confidence(domain_id, score);
