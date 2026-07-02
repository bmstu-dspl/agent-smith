package domain

import (
	"testing"
	"time"
)

func TestDocumentPublishFlow(t *testing.T) {
	now := time.Now().UTC()

	documentID, _ := NewDocumentID("doc-1")
	versionID, _ := NewVersionID("ver-1")
	chunkID, _ := NewChunkID("chunk-1")
	tenantID, _ := NewTenantID("tenant-1")
	sourceType, _ := NewSourceType("text")

	document, err := NewDocument(
		documentID,
		tenantID,
		"Knowledge Note",
		SourceMetadata{SourceType: sourceType},
		VisibilityTenant,
		now,
	)
	if err != nil {
		t.Fatalf("NewDocument returned error: %v", err)
	}

	version, err := NewDocumentVersion(
		versionID,
		documentID,
		tenantID,
		"Important text for memory.",
		SourceMetadata{SourceType: sourceType},
		TrustLevelTrusted,
		now,
	)
	if err != nil {
		t.Fatalf("NewDocumentVersion returned error: %v", err)
	}

	if err := document.AddVersion(version, now); err != nil {
		t.Fatalf("AddVersion returned error: %v", err)
	}

	chunk, err := NewChunk(chunkID, tenantID, versionID, 0, "Important text", 0, 14, VisibilityTenant)
	if err != nil {
		t.Fatalf("NewChunk returned error: %v", err)
	}

	if err := version.MarkProcessed([]Chunk{chunk}, now); err != nil {
		t.Fatalf("MarkProcessed returned error: %v", err)
	}
	if err := version.Approve(now); err != nil {
		t.Fatalf("Approve returned error: %v", err)
	}
	if err := document.PublishVersion(versionID, now); err != nil {
		t.Fatalf("PublishVersion returned error: %v", err)
	}

	if version.ReviewStatus() != ReviewStatusPublished {
		t.Fatalf("expected version status %q, got %q", ReviewStatusPublished, version.ReviewStatus())
	}
	if document.PublishedVersionID() == nil || *document.PublishedVersionID() != versionID {
		t.Fatalf("published version id mismatch")
	}
}
