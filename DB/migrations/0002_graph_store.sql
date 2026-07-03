CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    from_node_id TEXT NOT NULL REFERENCES graph_nodes (node_id) ON DELETE CASCADE,
    to_node_id TEXT NOT NULL REFERENCES graph_nodes (node_id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_from_node ON graph_edges (from_node_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_to_node ON graph_edges (to_node_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges (edge_type);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes (node_type);
