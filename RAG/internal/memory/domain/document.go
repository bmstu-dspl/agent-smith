package domain

import (
	"strings"
	"time"
)

type Document struct {
	id               DocumentID
	tenantID         TenantID
	title            string
	sourceMetadata   SourceMetadata
	visibility       Visibility
	publishedVersion *VersionID
	versions         map[VersionID]*DocumentVersion
	audit            AuditFields
}

func NewDocument(
	id DocumentID,
	tenantID TenantID,
	title string,
	sourceMetadata SourceMetadata,
	visibility Visibility,
	now time.Time,
) (*Document, error) {
	title = strings.TrimSpace(title)
	if title == "" {
		return nil, ErrEmptyTitle
	}

	return &Document{
		id:             id,
		tenantID:       tenantID,
		title:          title,
		sourceMetadata: sourceMetadata,
		visibility:     visibility,
		versions:       make(map[VersionID]*DocumentVersion),
		audit: AuditFields{
			CreatedAt: now,
			UpdatedAt: now,
		},
	}, nil
}

func (d *Document) AddVersion(version *DocumentVersion, now time.Time) error {
	if version.DocumentID() != d.id {
		return ErrVersionDocumentMismatch
	}
	if version.TenantID() != d.tenantID {
		return ErrVersionTenantMismatch
	}

	d.versions[version.ID()] = version
	d.audit.UpdatedAt = now
	return nil
}

func (d *Document) PublishVersion(versionID VersionID, now time.Time) error {
	version, ok := d.versions[versionID]
	if !ok {
		return ErrVersionNotPublishable
	}
	if d.publishedVersion != nil && *d.publishedVersion != versionID {
		return ErrPublishedVersionExists
	}
	if err := version.Publish(now); err != nil {
		return err
	}

	d.publishedVersion = &versionID
	d.audit.UpdatedAt = now
	return nil
}

func (d *Document) ArchiveVersion(versionID VersionID, now time.Time) error {
	version, ok := d.versions[versionID]
	if !ok {
		return ErrVersionArchived
	}
	if err := version.Archive(now); err != nil {
		return err
	}
	if d.publishedVersion != nil && *d.publishedVersion == versionID {
		d.publishedVersion = nil
	}
	d.audit.UpdatedAt = now
	return nil
}

func (d *Document) ID() DocumentID {
	return d.id
}

func (d *Document) TenantID() TenantID {
	return d.tenantID
}

func (d *Document) Title() string {
	return d.title
}

func (d *Document) SourceMetadata() SourceMetadata {
	return d.sourceMetadata
}

func (d *Document) Visibility() Visibility {
	return d.visibility
}

func (d *Document) PublishedVersionID() *VersionID {
	return d.publishedVersion
}

func (d *Document) Version(versionID VersionID) (*DocumentVersion, bool) {
	version, ok := d.versions[versionID]
	return version, ok
}

func (d *Document) Versions() []*DocumentVersion {
	versions := make([]*DocumentVersion, 0, len(d.versions))
	for _, version := range d.versions {
		versions = append(versions, version)
	}
	return versions
}

func (d *Document) Audit() AuditFields {
	return d.audit
}
