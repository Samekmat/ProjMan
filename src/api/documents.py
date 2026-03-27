import uuid
from typing import List

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import get_current_user
from src.api.schemas import DocumentCreate, DocumentResponse, DocumentUpdate
from src.db.connection import get_db_connection
from src.services.s3 import (
    delete_file_from_s3,
    generate_presigned_download_url,
    generate_presigned_upload_url,
)

router = APIRouter(tags=["Documents"])


@router.post("/project/{project_id}/documents", status_code=status.HTTP_201_CREATED)
async def create_document_upload_url(
    project_id: str,
    document: DocumentCreate,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Write file metadata into db and returns presigned url to AWS S3
    """
    role = await conn.fetchval(
        """
        SELECT role
        FROM project_users
        WHERE project_id = $1::uuid AND user_id = $2::uuid
        """,
        project_id,
        current_user_id,
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this project"
        )

    doc_id = str(uuid.uuid4())
    s3_key = f"projects/{project_id}/{doc_id}-{document.filename}"

    await conn.execute(
        """
        INSERT INTO documents (id, project_id, filename, s3_key, size_bytes)
        VALUES ($1::uuid, $2::uuid, $3, $4, 0)
        """,
        doc_id,
        project_id,
        document.filename,
        s3_key,
    )

    presigned_url = await generate_presigned_upload_url(
        object_name=s3_key, content_type=document.content_type
    )

    return {
        "document_id": doc_id,
        "upload_url": presigned_url,
        "message": "Use the upload_url to PUT your file directly to S3.",
    }


@router.get("/project/{project_id}/documents", response_model=List[DocumentResponse])
async def get_project_documents(
    project_id: str,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Fetch the document list for a project."""
    role = await conn.fetchval(
        """
        SELECT role FROM project_users
        WHERE project_id = $1::uuid AND user_id = $2::uuid
        """,
        project_id,
        current_user_id,
    )
    if not role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    docs = await conn.fetch(
        """
        SELECT id, project_id, filename, s3_key, size_bytes, created_at
        FROM documents
        WHERE project_id = $1::uuid
        ORDER BY created_at DESC
        """,
        project_id,
    )
    return [dict(d) for d in docs]


@router.get("/document/{document_id}")
async def download_document(
    document_id: str,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Generate a download link from S3 if the user has access to the project."""
    record = await conn.fetchrow(
        """
        SELECT d.s3_key
        FROM documents d
                 INNER JOIN project_users pu ON d.project_id = pu.project_id
        WHERE d.id = $1::uuid AND pu.user_id = $2::uuid
        """,
        document_id,
        current_user_id,
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied"
        )

    download_url = await generate_presigned_download_url(record["s3_key"])

    return {"download_url": download_url}


@router.delete("/document/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Delete a file from S3 bucket and database.
    Require 'owner' role in the specific project.
    """
    record = await conn.fetchrow(
        """
        SELECT d.s3_key, pu.role
        FROM documents d
                 INNER JOIN project_users pu ON d.project_id = pu.project_id
        WHERE d.id = $1::uuid AND pu.user_id = $2::uuid
        """,
        document_id,
        current_user_id,
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found or access denied"
        )

    if record["role"] != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner can delete documents",
        )

    await delete_file_from_s3(record["s3_key"])

    await conn.execute("DELETE FROM documents WHERE id = $1::uuid", document_id)

    return None


@router.put("/document/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    document_update: DocumentUpdate,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Update document name"""

    access = await conn.fetchval(
        """
        SELECT d.id
        FROM documents d
        INNER JOIN project_users pu ON d.project_id = pu.project_id
        WHERE d.id = $1::uuid AND pu.user_id = $2::uuid
        """,
        document_id,
        current_user_id,
    )

    if not access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    updated_document = await conn.fetchrow(
        """
        UPDATE documents
        SET filename = $1
        WHERE id = $2::uuid
        RETURNING id, project_id, filename, s3_key, size_bytes, created_at
        """,
        document_update.filename,
        document_id,
    )
    return dict(updated_document)
