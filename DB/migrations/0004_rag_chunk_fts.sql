CREATE INDEX IF NOT EXISTS idx_rag_chunks_text_fts
    ON rag_chunks
    USING GIN (to_tsvector('simple', text));
