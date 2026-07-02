package domain

import (
	"strings"
	"time"
)

type DocumentVersion struct {
	id             VersionID
	documentID     DocumentID
	tenantID       TenantID
	rawText        string
	sourceMetadata SourceMetadata
	trustLevel     TrustLevel
	reviewStatus   ReviewStatus
	chunks         []Chunk
	processedAt    *time.Time
	reviewedAt     *time.Time
	publishedAt    *time.Time
	audit          AuditFields
}

func NewDocumentVersion(
	id VersionID,
	documentID DocumentID,
	tenantID TenantID,
	rawText string,
	sourceMetadata SourceMetadata,
	trustLevel TrustLevel,
	now time.Time,
) (*DocumentVersion, error) {
	rawText = strings.TrimSpace(rawText)
	if rawText == "" {
		return nil, ErrEmptyRawText
	}

	return &DocumentVersion{
		id:             id,
		documentID:     documentID,
		tenantID:       tenantID,
		rawText:        rawText,
		sourceMetadata: sourceMetadata,
		trustLevel:     trustLevel,
		reviewStatus:   ReviewStatusDraft,
		audit: AuditFields{
			CreatedAt: now,
			UpdatedAt: now,
		},
	}, nil
}

func (v *DocumentVersion) MarkProcessed(chunks []Chunk, now time.Time) error {
	if v.reviewStatus == ReviewStatusArchived {
		return ErrVersionArchived
	}
	if v.reviewStatus != ReviewStatusDraft {
		return ErrVersionAlreadyProcessed
	}

	for _, chunk := range chunks {
		if chunk.TenantID() != v.tenantID {
			return ErrChunkTenantMismatch
		}
	}

	v.chunks = append([]Chunk(nil), chunks...)
	v.reviewStatus = ReviewStatusProcessed
	v.processedAt = ptrTime(now)
	v.audit.UpdatedAt = now
	return nil
}

func (v *DocumentVersion) Approve(now time.Time) error {
	if v.reviewStatus == ReviewStatusArchived {
		return ErrVersionArchived
	}
	if v.reviewStatus != ReviewStatusProcessed {
		return ErrVersionNotReviewable
	}

	v.reviewStatus = ReviewStatusApproved
	v.reviewedAt = ptrTime(now)
	v.audit.UpdatedAt = now
	return nil
}

func (v *DocumentVersion) Reject(now time.Time) error {
	if v.reviewStatus == ReviewStatusArchived {
		return ErrVersionArchived
	}
	if v.reviewStatus != ReviewStatusProcessed {
		return ErrVersionNotReviewable
	}

	v.reviewStatus = ReviewStatusRejected
	v.reviewedAt = ptrTime(now)
	v.audit.UpdatedAt = now
	return nil
}

func (v *DocumentVersion) Publish(now time.Time) error {
	if v.reviewStatus == ReviewStatusArchived {
		return ErrVersionArchived
	}
	if v.reviewStatus == ReviewStatusRejected {
		return ErrVersionRejected
	}
	if v.reviewStatus != ReviewStatusApproved {
		return ErrVersionNotPublishable
	}

	v.reviewStatus = ReviewStatusPublished
	v.publishedAt = ptrTime(now)
	v.audit.UpdatedAt = now
	return nil
}

func (v *DocumentVersion) Archive(now time.Time) error {
	v.reviewStatus = ReviewStatusArchived
	v.audit.UpdatedAt = now
	return nil
}

func (v *DocumentVersion) ID() VersionID {
	return v.id
}

func (v *DocumentVersion) DocumentID() DocumentID {
	return v.documentID
}

func (v *DocumentVersion) TenantID() TenantID {
	return v.tenantID
}

func (v *DocumentVersion) RawText() string {
	return v.rawText
}

func (v *DocumentVersion) SourceMetadata() SourceMetadata {
	return v.sourceMetadata
}

func (v *DocumentVersion) TrustLevel() TrustLevel {
	return v.trustLevel
}

func (v *DocumentVersion) ReviewStatus() ReviewStatus {
	return v.reviewStatus
}

func (v *DocumentVersion) Chunks() []Chunk {
	return append([]Chunk(nil), v.chunks...)
}

func (v *DocumentVersion) ProcessedAt() *time.Time {
	return v.processedAt
}

func (v *DocumentVersion) ReviewedAt() *time.Time {
	return v.reviewedAt
}

func (v *DocumentVersion) PublishedAt() *time.Time {
	return v.publishedAt
}

func (v *DocumentVersion) Audit() AuditFields {
	return v.audit
}

func ptrTime(value time.Time) *time.Time {
	return &value
}
