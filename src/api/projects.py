from datetime import datetime, timedelta, timezone
from typing import List

import asyncpg
import jwt
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import get_current_user
from src.api.schemas import ProjectCreate, ProjectResponse, ProjectUpdate
from src.core.config import settings
from src.db.connection import get_db_connection

router = APIRouter(tags=["Projects"])


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Creates a new project and automatically assign an owner role to it.
    """
    async with conn.transaction():
        project_id = await conn.fetchval(
            """
            INSERT INTO projects (name, description)
            VALUES ($1, $2)
            RETURNING id
            """,
            project.name,
            project.description,
        )

        await conn.execute(
            """
            INSERT INTO project_users (project_id, user_id, role)
            VALUES ($1::uuid, $2::uuid, 'owner')
            """,
            str(project_id),
            current_user_id,
        )
    return {"message": "Project created successfully", "project_id": project_id}


@router.get("/projects", response_model=List[ProjectResponse])
async def get_my_projects(
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Fetch a projects list that is accessible for the user.
    Including full info: details + documents.
    """
    projects_records = await conn.fetch(
        """
        SELECT 
            p.id, p.name, p.description, p.total_storage_bytes,
            COALESCE(
                JSON_AGG(
                    JSON_BUILD_OBJECT(
                        'id', d.id,
                        'project_id', d.project_id,
                        'filename', d.filename,
                        's3_key', d.s3_key,
                        'size_bytes', d.size_bytes,
                        'created_at', d.created_at
                    )
                ) FILTER (WHERE d.id IS NOT NULL), '[]'
            ) AS documents
        FROM projects p
        INNER JOIN project_users pu ON p.id = pu.project_id
        LEFT JOIN documents d ON p.id = d.project_id
        WHERE pu.user_id = $1::uuid
        GROUP BY p.id
        ORDER BY p.created_at DESC
        """,
        current_user_id,
    )

    import json

    results = []
    for p in projects_records:
        p_dict = dict(p)
        if isinstance(p_dict["documents"], str):
            p_dict["documents"] = json.loads(p_dict["documents"])
        results.append(p_dict)

    return results


@router.delete("/project/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Delete a project. Requires to be an owner of the project."""
    role = await conn.fetchval(
        """
        SELECT role FROM project_users
        WHERE project_id = $1::uuid AND user_id = $2::uuid
        """,
        project_id,
        current_user_id,
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not an owner of this project",
        )

    await conn.execute("DELETE FROM projects WHERE id = $1::uuid", project_id)
    return {"message": "Project deleted successfully"}


@router.post("/project/{project_id}/invite", status_code=status.HTTP_200_OK)
async def invite_user_to_project(
    project_id: str,
    user: str,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Adds a given user (login) to the project with a role participant.
    It requires an inviter to be a project owner."""
    role = await conn.fetchval(
        """
        SELECT role FROM project_users
        WHERE project_id = $1::uuid AND user_id = $2::uuid
        """,
        project_id,
        current_user_id,
    )

    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner can invite other users",
        )

    target_user = await conn.fetchrow("SELECT id FROM users WHERE login = $1", user)

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with login '{user}' not found",
        )

    target_user_id = target_user["id"]

    if str(target_user_id) == current_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot invite yourself to the project",
        )

    existing_role = await conn.fetchval(
        """
    SELECT role FROM project_users
    WHERE project_id = $1::uuid AND user_id = $2::uuid
    """,
        project_id,
        target_user_id,
    )

    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User '{user}' is already a {existing_role} in this project",
        )

    await conn.execute(
        """
        INSERT INTO project_users (project_id, user_id, role)
        VALUES ($1::uuid, $2::uuid, 'participant')
        """,
        project_id,
        target_user_id,
    )
    return {"message": f"User '{user}' invited successfully"}


@router.get("/project/{project_id}/info", response_model=ProjectResponse)
async def get_project_info(
    project_id: str,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Return project details info"""

    record = await conn.fetchrow(
        """
        SELECT p.id, p.name, p.description, p.total_storage_bytes
        FROM projects p
        INNER JOIN project_users pu ON p.id = pu.project_id
        WHERE p.id = $1::uuid AND pu.user_id = $2::uuid
        """,
        project_id,
        current_user_id,
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    return dict(record)


@router.put("/project/{project_id}/info", response_model=ProjectResponse)
async def update_project_info(
    project_id: str,
    project_update: ProjectUpdate,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Update name and/or descriprion of the project.
    Available for the owner and participant roles.
    """
    role = await conn.fetchval(
        """
        SELECT role FROM project_users
        WHERE project_id = $1::uuid AND user_id = $2::uuid
        """,
        project_id,
        current_user_id,
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    updated_record = await conn.fetchrow(
        """
        UPDATE projects
        SET name = COALESCE($1, name),
            description = COALESCE($2, description)
        WHERE id = $3::uuid
        RETURNING id, name, description, total_storage_bytes
        """,
        project_update.name,
        project_update.description,
        project_id,
    )

    return dict(updated_record)


@router.get("/project/{project_id}/share")
async def share_project_via_email(
    project_id: str,
    email: str,
    current_user_id: str = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Generate a safe link with an inviting token for the given email.
    Require 'owner' role.
    """
    role = await conn.fetchval(
        """
        SELECT role FROM project_users
        WHERE project_id = $1::uuid AND user_id = $2::uuid
        """,
        project_id,
        current_user_id,
    )

    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can share the project",
        )

    expire = datetime.now(timezone.utc) + timedelta(hours=48)

    to_encode = {
        "exp": expire,
        "project_id": project_id,
        "email": email,
        "type": "invite",
    }

    encoded_token = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )

    join_link = f"http://127.0.0.1:8000/join?token={encoded_token}"

    return {"message": f"Email conceptually sent to {email}", "join_link": join_link}


join_router = APIRouter(tags=["Join"])


@join_router.get("/join")
async def join_project_via_link(
    token: str, conn: asyncpg.Connection = Depends(get_db_connection)
):
    """Endpoint for email invited user."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )

        if payload.get("type") != "invite":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token type"
            )

        project_id = payload.get("project_id")
        email = payload.get("email")

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    target_user = await conn.fetchrow("SELECT id FROM users WHERE login = $1", email)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with this email/login must register first",
        )

    await conn.execute(
        """
        INSERT INTO project_users (project_id, user_id, role)
        VALUES ($1::uuid, $2::uuid, 'participant')
        ON CONFLICT (project_id, user_id) DO NOTHING
        """,
        project_id,
        target_user["id"],
    )

    return {"message": f"Successfully joined project {project_id} as participant"}
