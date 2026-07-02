package domain

import "time"

type DomainEvent interface {
	EventName() string
	OccurredAt() time.Time
}

type DocumentCreated struct {
	DocumentID DocumentID
	TenantID   TenantID
	At         time.Time
}

func (e DocumentCreated) EventName() string {
	return "memory.document.created"
}

func (e DocumentCreated) OccurredAt() time.Time {
	return e.At
}

type DocumentVersionAdded struct {
	DocumentID DocumentID
	VersionID  VersionID
	TenantID   TenantID
	At         time.Time
}

func (e DocumentVersionAdded) EventName() string {
	return "memory.document.version_added"
}

func (e DocumentVersionAdded) OccurredAt() time.Time {
	return e.At
}

type DocumentVersionPublished struct {
	DocumentID DocumentID
	VersionID  VersionID
	TenantID   TenantID
	At         time.Time
}

func (e DocumentVersionPublished) EventName() string {
	return "memory.document.version_published"
}

func (e DocumentVersionPublished) OccurredAt() time.Time {
	return e.At
}
