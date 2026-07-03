CREATE TABLE IF NOT EXISTS rag_documents (
    document_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    visibility TEXT NOT NULL,
    published_version_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);

CREATE TABLE IF NOT EXISTS rag_document_versions (
    version_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    trust_level TEXT NOT NULL,
    review_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NULL,
    reviewed_at TIMESTAMPTZ NULL,
    published_at TIMESTAMPTZ NULL,
    PRIMARY KEY (tenant_id, version_id),
    CONSTRAINT fk_rag_document_versions_document
        FOREIGN KEY (tenant_id, document_id)
        REFERENCES rag_documents (tenant_id, document_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_byte INTEGER NOT NULL,
    end_byte INTEGER NOT NULL,
    visibility TEXT NOT NULL,
    PRIMARY KEY (tenant_id, chunk_id),
    CONSTRAINT fk_rag_chunks_version
        FOREIGN KEY (tenant_id, version_id)
        REFERENCES rag_document_versions (tenant_id, version_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rag_versions_document ON rag_document_versions (tenant_id, document_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_version ON rag_chunks (tenant_id, version_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_published_version ON rag_documents (tenant_id, published_version_id);
