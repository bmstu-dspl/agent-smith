from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from ._domain import Document


class DocumentStore(Protocol):
    def save(self, document: Document) -> None: ...

    def get(self, tenant_id: str, document_id: str) -> Document | None: ...


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], Document] = {}

    def save(self, document: Document) -> None:
        self._documents[(document.tenant_id, document.document_id)] = deepcopy(document)

    def get(self, tenant_id: str, document_id: str) -> Document | None:
        document = self._documents.get((tenant_id.strip(), document_id.strip()))
        return deepcopy(document) if document is not None else None
