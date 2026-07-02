package domain

import "strings"

type Chunk struct {
	id         ChunkID
	tenantID   TenantID
	versionID  VersionID
	index      int
	text       string
	startByte  int
	endByte    int
	visibility Visibility
}

func NewChunk(
	id ChunkID,
	tenantID TenantID,
	versionID VersionID,
	index int,
	text string,
	startByte int,
	endByte int,
	visibility Visibility,
) (Chunk, error) {
	text = strings.TrimSpace(text)
	if text == "" {
		return Chunk{}, ErrEmptyChunkText
	}
	if index < 0 {
		return Chunk{}, ErrChunkIndexNegative
	}
	if startByte < 0 {
		return Chunk{}, ErrChunkStartNegative
	}
	if endByte <= startByte {
		return Chunk{}, ErrChunkEndBeforeStart
	}

	return Chunk{
		id:         id,
		tenantID:   tenantID,
		versionID:  versionID,
		index:      index,
		text:       text,
		startByte:  startByte,
		endByte:    endByte,
		visibility: visibility,
	}, nil
}

func (c Chunk) ID() ChunkID {
	return c.id
}

func (c Chunk) TenantID() TenantID {
	return c.tenantID
}

func (c Chunk) VersionID() VersionID {
	return c.versionID
}

func (c Chunk) Index() int {
	return c.index
}

func (c Chunk) Text() string {
	return c.text
}

func (c Chunk) StartByte() int {
	return c.startByte
}

func (c Chunk) EndByte() int {
	return c.endByte
}

func (c Chunk) Visibility() Visibility {
	return c.visibility
}
