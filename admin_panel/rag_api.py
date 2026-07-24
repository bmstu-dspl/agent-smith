from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from RAG import (
    ApproveVersionCommand,
    ArchiveVersionCommand,
    DeleteDocumentCommand,
    DeleteVersionCommand,
    DocumentNotFoundError,
    GetDocumentQuery,
    GetVersionChunksQuery,
    IngestFileDocumentCommand,
    IngestTextDocumentCommand,
    ListDocumentsQuery,
    MemoryError as RagMemoryError,
    PublishVersionCommand,
    RejectVersionCommand,
    SearchPublishedMemoryQuery,
    VectorizeVersionCommand,
)


class TextDocumentIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=500)
    version_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=1000)
    text: str = Field(min_length=1)
    visibility: str = Field(default="tenant", min_length=1, max_length=100)
    trust_level: str = Field(default="unknown", min_length=1, max_length=100)
    external_ref: str = Field(default="", max_length=2000)


def create_rag_router(require_identity, require_mutation_access) -> APIRouter:
    router = APIRouter(prefix="/admin/api/rag", tags=["admin-rag"])

    @router.post("/documents/text", status_code=status.HTTP_201_CREATED)
    async def ingest_text(request: Request, payload: TextDocumentIngestRequest) -> dict:
        require_mutation_access(request, required_role="editor")
        rag_settings = request.app.state.settings_store.get_rag().settings
        result = await _rag_call(
            request,
            "ingest_text_document",
            IngestTextDocumentCommand(
                document_id=payload.document_id,
                version_id=payload.version_id,
                tenant_id=payload.tenant_id,
                title=payload.title,
                raw_text=payload.text,
                visibility=payload.visibility,
                trust_level=payload.trust_level,
                chunk_visibility=payload.visibility,
                external_ref=payload.external_ref,
                max_chunk_chars=rag_settings.max_chunk_chars,
                chunk_overlap_chars=rag_settings.chunk_overlap_chars,
            ),
        )
        return _asdict(result)

    @router.post("/documents/file", status_code=status.HTTP_201_CREATED)
    async def ingest_file(
        request: Request,
        tenant_id: str = Form(...),
        document_id: str = Form(...),
        version_id: str = Form(...),
        title: str = Form(...),
        visibility: str = Form("tenant"),
        trust_level: str = Form("unknown"),
        external_ref: str = Form(""),
        file: UploadFile = File(...),
    ) -> dict:
        require_mutation_access(request, required_role="editor")
        content = await file.read()
        rag_settings = request.app.state.settings_store.get_rag().settings
        result = await _rag_call(
            request,
            "ingest_file_document",
            IngestFileDocumentCommand(
                document_id=document_id,
                version_id=version_id,
                tenant_id=tenant_id,
                title=title,
                file_name=file.filename or "upload",
                file_content=content,
                visibility=visibility,
                trust_level=trust_level,
                chunk_visibility=visibility,
                external_ref=external_ref,
                max_chunk_chars=rag_settings.max_chunk_chars,
                chunk_overlap_chars=rag_settings.chunk_overlap_chars,
            ),
        )
        return _asdict(result)

    @router.get("/documents")
    async def list_documents(
        request: Request,
        tenant_id: str = Query(min_length=1),
        review_status: str | None = None,
        visibility: str | None = None,
        source_type: str | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        require_identity(request)
        documents = await _rag_call(
            request,
            "list_documents",
            ListDocumentsQuery(
                tenant_id=tenant_id,
                review_status=review_status,
                visibility=visibility,
                source_type=source_type,
                limit=limit,
                offset=offset,
            ),
        )
        return {"documents": [_asdict(item) for item in documents]}

    @router.get("/documents/{document_id}")
    async def get_document(request: Request, document_id: str, tenant_id: str) -> dict:
        require_identity(request)
        result = await _rag_call(
            request,
            "get_document",
            GetDocumentQuery(tenant_id=tenant_id, document_id=document_id),
        )
        return _asdict(result)

    @router.get("/documents/{document_id}/versions/{version_id}/chunks")
    async def get_chunks(
        request: Request,
        document_id: str,
        version_id: str,
        tenant_id: str,
    ) -> dict:
        require_identity(request)
        chunks = await _rag_call(
            request,
            "get_version_chunks",
            GetVersionChunksQuery(
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
            ),
        )
        return {"chunks": [_asdict(item) for item in chunks]}

    @router.post("/documents/{document_id}/versions/{version_id}/{action}")
    async def version_action(
        request: Request,
        document_id: str,
        version_id: str,
        action: str,
        tenant_id: str,
    ) -> dict:
        require_mutation_access(request, required_role="editor")
        commands = {
            "approve": ("approve_version", ApproveVersionCommand),
            "reject": ("reject_version", RejectVersionCommand),
            "publish": ("publish_version", PublishVersionCommand),
            "archive": ("archive_version", ArchiveVersionCommand),
            "vectorize": ("vectorize_version", VectorizeVersionCommand),
        }
        selected = commands.get(action)
        if selected is None:
            raise HTTPException(status_code=404, detail="unknown RAG version action")
        method_name, command_type = selected
        result = await _rag_call(
            request,
            method_name,
            command_type(
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
            ),
        )
        if isinstance(result, tuple):
            return {"chunks": [_asdict(item) for item in result]}
        return _asdict(result)

    @router.delete(
        "/documents/{document_id}/versions/{version_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_version(
        request: Request,
        document_id: str,
        version_id: str,
        tenant_id: str,
    ) -> Response:
        require_mutation_access(request, required_role="editor")
        await _rag_call(
            request,
            "delete_version",
            DeleteVersionCommand(
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
            ),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.delete(
        "/documents/{document_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_document(
        request: Request,
        document_id: str,
        tenant_id: str,
    ) -> Response:
        require_mutation_access(request, required_role="editor")
        await _rag_call(
            request,
            "delete_document",
            DeleteDocumentCommand(tenant_id=tenant_id, document_id=document_id),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/search")
    async def search(request: Request, tenant_id: str, query: str) -> dict:
        require_identity(request)
        rag_settings = request.app.state.settings_store.get_rag().settings
        results = await _rag_call(
            request,
            "search_published_memory",
            SearchPublishedMemoryQuery(
                tenant_id=tenant_id,
                query=query,
                limit=rag_settings.limit,
                retrieval_mode=rag_settings.retrieval_mode,
            ),
        )
        return {"results": [_asdict(item) for item in results]}

    return router


async def _rag_call(request: Request, method_name: str, argument):
    method = getattr(request.app.state.rag_memory, method_name)
    try:
        return await asyncio.to_thread(method, argument)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RagMemoryError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _asdict(value) -> dict:
    return asdict(value)
