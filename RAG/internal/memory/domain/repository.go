package domain

import "context"

type DocumentRepository interface {
	Save(ctx context.Context, document *Document) error
	FindByID(ctx context.Context, tenantID TenantID, documentID DocumentID) (*Document, error)
}
