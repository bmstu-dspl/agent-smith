package application

import (
	"context"
	"testing"
	"time"

	"rag/internal/memory/domain"
)

func TestServiceDocumentLifecycle(t *testing.T) {
	fixedNow := time.Date(2026, 7, 2, 12, 0, 0, 0, time.UTC)
	service := NewService(newInMemoryDocumentRepository(), fixedClock{now: fixedNow})
	ctx := context.Background()

	document, err := service.CreateDocument(ctx, CreateDocumentCommand{
		DocumentID:   "doc-1",
		TenantID:     "tenant-1",
		Title:        "Architecture Notes",
		SourceType:   "text",
		OriginalName: "notes.txt",
		Visibility:   "tenant",
	})
	if err != nil {
		t.Fatalf("CreateDocument returned error: %v", err)
	}
	if document.VersionCount != 0 {
		t.Fatalf("expected empty document versions, got %d", document.VersionCount)
	}

	version, err := service.AddDocumentVersion(ctx, AddDocumentVersionCommand{
		DocumentID:   "doc-1",
		VersionID:    "ver-1",
		TenantID:     "tenant-1",
		RawText:      "This is a long-term memory note.",
		SourceType:   "text",
		OriginalName: "notes.txt",
		TrustLevel:   "trusted",
	})
	if err != nil {
		t.Fatalf("AddDocumentVersion returned error: %v", err)
	}
	if version.ReviewStatus != "draft" {
		t.Fatalf("expected draft review status, got %s", version.ReviewStatus)
	}

	version, err = service.MarkVersionProcessed(ctx, MarkVersionProcessedCommand{
		DocumentID: "doc-1",
		VersionID:  "ver-1",
		TenantID:   "tenant-1",
		Chunks: []ChunkInput{
			{
				ChunkID:    "chunk-1",
				Index:      0,
				Text:       "This is a long-term memory note.",
				StartByte:  0,
				EndByte:    32,
				Visibility: "tenant",
			},
		},
	})
	if err != nil {
		t.Fatalf("MarkVersionProcessed returned error: %v", err)
	}
	if version.ReviewStatus != "processed" {
		t.Fatalf("expected processed status, got %s", version.ReviewStatus)
	}
	if version.ChunkCount != 1 {
		t.Fatalf("expected one chunk, got %d", version.ChunkCount)
	}

	version, err = service.ApproveVersion(ctx, ApproveVersionCommand{
		DocumentID: "doc-1",
		VersionID:  "ver-1",
		TenantID:   "tenant-1",
	})
	if err != nil {
		t.Fatalf("ApproveVersion returned error: %v", err)
	}
	if version.ReviewStatus != "approved" {
		t.Fatalf("expected approved status, got %s", version.ReviewStatus)
	}

	version, err = service.PublishVersion(ctx, PublishVersionCommand{
		DocumentID: "doc-1",
		VersionID:  "ver-1",
		TenantID:   "tenant-1",
	})
	if err != nil {
		t.Fatalf("PublishVersion returned error: %v", err)
	}
	if version.ReviewStatus != "published" {
		t.Fatalf("expected published status, got %s", version.ReviewStatus)
	}
	if version.PublishedAt == nil || !version.PublishedAt.Equal(fixedNow) {
		t.Fatalf("expected published timestamp %s", fixedNow)
	}
}

type fixedClock struct {
	now time.Time
}

func (c fixedClock) Now() time.Time {
	return c.now
}

type inMemoryDocumentRepository struct {
	documents map[string]*domain.Document
}

func newInMemoryDocumentRepository() *inMemoryDocumentRepository {
	return &inMemoryDocumentRepository{
		documents: make(map[string]*domain.Document),
	}
}

func (r *inMemoryDocumentRepository) Save(_ context.Context, document *domain.Document) error {
	key := repositoryKey(document.TenantID(), document.ID())
	r.documents[key] = document
	return nil
}

func (r *inMemoryDocumentRepository) FindByID(_ context.Context, tenantID domain.TenantID, documentID domain.DocumentID) (*domain.Document, error) {
	return r.documents[repositoryKey(tenantID, documentID)], nil
}

func repositoryKey(tenantID domain.TenantID, documentID domain.DocumentID) string {
	return string(tenantID) + "::" + string(documentID)
}
