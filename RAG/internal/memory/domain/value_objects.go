package domain

import (
	"strings"
	"time"
)

type DocumentID string

func NewDocumentID(value string) (DocumentID, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return "", ErrEmptyDocumentID
	}
	return DocumentID(value), nil
}

type VersionID string

func NewVersionID(value string) (VersionID, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return "", ErrEmptyVersionID
	}
	return VersionID(value), nil
}

type ChunkID string

func NewChunkID(value string) (ChunkID, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return "", ErrEmptyChunkID
	}
	return ChunkID(value), nil
}

type TenantID string

func NewTenantID(value string) (TenantID, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return "", ErrEmptyTenantID
	}
	return TenantID(value), nil
}

type SourceType string

const (
	SourceTypeText SourceType = "text"
	SourceTypePDF  SourceType = "pdf"
	SourceTypeDOCX SourceType = "docx"
	SourceTypeMD   SourceType = "md"
	SourceTypeHTML SourceType = "html"
)

func NewSourceType(value string) (SourceType, error) {
	sourceType := SourceType(strings.TrimSpace(strings.ToLower(value)))
	switch sourceType {
	case SourceTypeText, SourceTypePDF, SourceTypeDOCX, SourceTypeMD, SourceTypeHTML:
		return sourceType, nil
	default:
		return "", ErrEmptySourceType
	}
}

type TrustLevel string

const (
	TrustLevelUnknown   TrustLevel = "unknown"
	TrustLevelLow       TrustLevel = "low"
	TrustLevelTrusted   TrustLevel = "trusted"
	TrustLevelCanonical TrustLevel = "canonical"
)

func NewTrustLevel(value string) (TrustLevel, error) {
	level := TrustLevel(strings.TrimSpace(strings.ToLower(value)))
	switch level {
	case TrustLevelUnknown, TrustLevelLow, TrustLevelTrusted, TrustLevelCanonical:
		return level, nil
	default:
		return "", ErrInvalidTrustLevel
	}
}

type ReviewStatus string

const (
	ReviewStatusDraft     ReviewStatus = "draft"
	ReviewStatusProcessed ReviewStatus = "processed"
	ReviewStatusApproved  ReviewStatus = "approved"
	ReviewStatusRejected  ReviewStatus = "rejected"
	ReviewStatusPublished ReviewStatus = "published"
	ReviewStatusArchived  ReviewStatus = "archived"
)

func NewReviewStatus(value string) (ReviewStatus, error) {
	status := ReviewStatus(strings.TrimSpace(strings.ToLower(value)))
	switch status {
	case ReviewStatusDraft, ReviewStatusProcessed, ReviewStatusApproved, ReviewStatusRejected, ReviewStatusPublished, ReviewStatusArchived:
		return status, nil
	default:
		return "", ErrInvalidReviewStatus
	}
}

type Visibility string

const (
	VisibilityPrivate    Visibility = "private"
	VisibilityRestricted Visibility = "restricted"
	VisibilityTenant     Visibility = "tenant"
)

func NewVisibility(value string) (Visibility, error) {
	visibility := Visibility(strings.TrimSpace(strings.ToLower(value)))
	switch visibility {
	case VisibilityPrivate, VisibilityRestricted, VisibilityTenant:
		return visibility, nil
	default:
		return "", ErrInvalidVisibility
	}
}

type SourceMetadata struct {
	SourceType   SourceType
	ExternalRef  string
	OriginalName string
}

type AuditFields struct {
	CreatedAt time.Time
	UpdatedAt time.Time
}
