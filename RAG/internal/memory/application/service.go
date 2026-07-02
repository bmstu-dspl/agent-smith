package application

import (
	"context"
	"errors"
	"time"

	"rag/internal/memory/domain"
)

var ErrDocumentNotFound = errors.New("document not found")

type Clock interface {
	Now() time.Time
}

type Service struct {
	documents domain.DocumentRepository
	clock     Clock
}

func NewService(documents domain.DocumentRepository, clock Clock) *Service {
	return &Service{
		documents: documents,
		clock:     clock,
	}
}

type CreateDocumentCommand struct {
	DocumentID   string
	TenantID     string
	Title        string
	SourceType   string
	ExternalRef  string
	OriginalName string
	Visibility   string
}

type AddDocumentVersionCommand struct {
	DocumentID   string
	VersionID    string
	TenantID     string
	RawText      string
	SourceType   string
	ExternalRef  string
	OriginalName string
	TrustLevel   string
}

type MarkVersionProcessedCommand struct {
	DocumentID string
	VersionID  string
	TenantID   string
	Chunks     []ChunkInput
}

type ApproveVersionCommand struct {
	DocumentID string
	VersionID  string
	TenantID   string
}

type PublishVersionCommand struct {
	DocumentID string
	VersionID  string
	TenantID   string
}

type ChunkInput struct {
	ChunkID    string
	Index      int
	Text       string
	StartByte  int
	EndByte    int
	Visibility string
}

type DocumentDTO struct {
	DocumentID         string
	TenantID           string
	Title              string
	Visibility         string
	PublishedVersionID *string
	VersionCount       int
}

type DocumentVersionDTO struct {
	VersionID    string
	DocumentID   string
	TenantID     string
	ReviewStatus string
	TrustLevel   string
	ChunkCount   int
	ProcessedAt  *time.Time
	ReviewedAt   *time.Time
	PublishedAt  *time.Time
	SourceType   string
	ExternalRef  string
	OriginalName string
}

func (s *Service) CreateDocument(ctx context.Context, cmd CreateDocumentCommand) (*DocumentDTO, error) {
	documentID, err := domain.NewDocumentID(cmd.DocumentID)
	if err != nil {
		return nil, err
	}
	tenantID, err := domain.NewTenantID(cmd.TenantID)
	if err != nil {
		return nil, err
	}
	sourceType, err := domain.NewSourceType(cmd.SourceType)
	if err != nil {
		return nil, err
	}
	visibility, err := domain.NewVisibility(cmd.Visibility)
	if err != nil {
		return nil, err
	}

	now := s.clock.Now()
	document, err := domain.NewDocument(
		documentID,
		tenantID,
		cmd.Title,
		domain.SourceMetadata{
			SourceType:   sourceType,
			ExternalRef:  cmd.ExternalRef,
			OriginalName: cmd.OriginalName,
		},
		visibility,
		now,
	)
	if err != nil {
		return nil, err
	}

	if err := s.documents.Save(ctx, document); err != nil {
		return nil, err
	}

	return toDocumentDTO(document), nil
}

func (s *Service) AddDocumentVersion(ctx context.Context, cmd AddDocumentVersionCommand) (*DocumentVersionDTO, error) {
	document, err := s.loadDocument(ctx, cmd.TenantID, cmd.DocumentID)
	if err != nil {
		return nil, err
	}

	versionID, err := domain.NewVersionID(cmd.VersionID)
	if err != nil {
		return nil, err
	}
	documentID, err := domain.NewDocumentID(cmd.DocumentID)
	if err != nil {
		return nil, err
	}
	tenantID, err := domain.NewTenantID(cmd.TenantID)
	if err != nil {
		return nil, err
	}
	sourceType, err := domain.NewSourceType(cmd.SourceType)
	if err != nil {
		return nil, err
	}
	trustLevel, err := domain.NewTrustLevel(cmd.TrustLevel)
	if err != nil {
		return nil, err
	}

	now := s.clock.Now()
	version, err := domain.NewDocumentVersion(
		versionID,
		documentID,
		tenantID,
		cmd.RawText,
		domain.SourceMetadata{
			SourceType:   sourceType,
			ExternalRef:  cmd.ExternalRef,
			OriginalName: cmd.OriginalName,
		},
		trustLevel,
		now,
	)
	if err != nil {
		return nil, err
	}

	if err := document.AddVersion(version, now); err != nil {
		return nil, err
	}
	if err := s.documents.Save(ctx, document); err != nil {
		return nil, err
	}

	return toDocumentVersionDTO(version), nil
}

func (s *Service) MarkVersionProcessed(ctx context.Context, cmd MarkVersionProcessedCommand) (*DocumentVersionDTO, error) {
	document, version, err := s.loadDocumentVersion(ctx, cmd.TenantID, cmd.DocumentID, cmd.VersionID)
	if err != nil {
		return nil, err
	}

	chunks, err := s.toChunks(cmd.TenantID, cmd.VersionID, cmd.Chunks)
	if err != nil {
		return nil, err
	}

	now := s.clock.Now()
	if err := version.MarkProcessed(chunks, now); err != nil {
		return nil, err
	}
	if err := s.documents.Save(ctx, document); err != nil {
		return nil, err
	}

	return toDocumentVersionDTO(version), nil
}

func (s *Service) ApproveVersion(ctx context.Context, cmd ApproveVersionCommand) (*DocumentVersionDTO, error) {
	document, version, err := s.loadDocumentVersion(ctx, cmd.TenantID, cmd.DocumentID, cmd.VersionID)
	if err != nil {
		return nil, err
	}

	now := s.clock.Now()
	if err := version.Approve(now); err != nil {
		return nil, err
	}
	if err := s.documents.Save(ctx, document); err != nil {
		return nil, err
	}

	return toDocumentVersionDTO(version), nil
}

func (s *Service) PublishVersion(ctx context.Context, cmd PublishVersionCommand) (*DocumentVersionDTO, error) {
	document, version, err := s.loadDocumentVersion(ctx, cmd.TenantID, cmd.DocumentID, cmd.VersionID)
	if err != nil {
		return nil, err
	}

	now := s.clock.Now()
	if err := document.PublishVersion(version.ID(), now); err != nil {
		return nil, err
	}
	if err := s.documents.Save(ctx, document); err != nil {
		return nil, err
	}

	return toDocumentVersionDTO(version), nil
}

func (s *Service) loadDocument(ctx context.Context, tenantValue string, documentValue string) (*domain.Document, error) {
	tenantID, err := domain.NewTenantID(tenantValue)
	if err != nil {
		return nil, err
	}
	documentID, err := domain.NewDocumentID(documentValue)
	if err != nil {
		return nil, err
	}

	document, err := s.documents.FindByID(ctx, tenantID, documentID)
	if err != nil {
		return nil, err
	}
	if document == nil {
		return nil, ErrDocumentNotFound
	}
	return document, nil
}

func (s *Service) loadDocumentVersion(ctx context.Context, tenantValue string, documentValue string, versionValue string) (*domain.Document, *domain.DocumentVersion, error) {
	document, err := s.loadDocument(ctx, tenantValue, documentValue)
	if err != nil {
		return nil, nil, err
	}

	versionID, err := domain.NewVersionID(versionValue)
	if err != nil {
		return nil, nil, err
	}

	version, ok := document.Version(versionID)
	if !ok {
		return nil, nil, domain.ErrVersionNotFound
	}

	return document, version, nil
}

func (s *Service) toChunks(tenantValue string, versionValue string, inputs []ChunkInput) ([]domain.Chunk, error) {
	tenantID, err := domain.NewTenantID(tenantValue)
	if err != nil {
		return nil, err
	}
	versionID, err := domain.NewVersionID(versionValue)
	if err != nil {
		return nil, err
	}

	chunks := make([]domain.Chunk, 0, len(inputs))
	for _, input := range inputs {
		chunkID, err := domain.NewChunkID(input.ChunkID)
		if err != nil {
			return nil, err
		}
		visibility, err := domain.NewVisibility(input.Visibility)
		if err != nil {
			return nil, err
		}
		chunk, err := domain.NewChunk(
			chunkID,
			tenantID,
			versionID,
			input.Index,
			input.Text,
			input.StartByte,
			input.EndByte,
			visibility,
		)
		if err != nil {
			return nil, err
		}
		chunks = append(chunks, chunk)
	}

	return chunks, nil
}

func toDocumentDTO(document *domain.Document) *DocumentDTO {
	var publishedVersionID *string
	if document.PublishedVersionID() != nil {
		value := string(*document.PublishedVersionID())
		publishedVersionID = &value
	}

	return &DocumentDTO{
		DocumentID:         string(document.ID()),
		TenantID:           string(document.TenantID()),
		Title:              document.Title(),
		Visibility:         string(document.Visibility()),
		PublishedVersionID: publishedVersionID,
		VersionCount:       len(document.Versions()),
	}
}

func toDocumentVersionDTO(version *domain.DocumentVersion) *DocumentVersionDTO {
	metadata := version.SourceMetadata()

	return &DocumentVersionDTO{
		VersionID:    string(version.ID()),
		DocumentID:   string(version.DocumentID()),
		TenantID:     string(version.TenantID()),
		ReviewStatus: string(version.ReviewStatus()),
		TrustLevel:   string(version.TrustLevel()),
		ChunkCount:   len(version.Chunks()),
		ProcessedAt:  version.ProcessedAt(),
		ReviewedAt:   version.ReviewedAt(),
		PublishedAt:  version.PublishedAt(),
		SourceType:   string(metadata.SourceType),
		ExternalRef:  metadata.ExternalRef,
		OriginalName: metadata.OriginalName,
	}
}
