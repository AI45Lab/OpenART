-- document_index_registry schema
CREATE TABLE IF NOT EXISTS document_registry (
    doc_id TEXT PRIMARY KEY,
    source_class TEXT NOT NULL,
    source_path TEXT NOT NULL,
    checksum TEXT,
    ingest_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doc_tags (
    doc_id TEXT,
    tag TEXT,
    PRIMARY KEY (doc_id, tag)
);
