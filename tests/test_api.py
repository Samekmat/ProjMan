from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from src.db.connection import get_db_connection
from src.main import app

client = TestClient(app)


def test_app_starts_and_serves_docs():
    """Tests If app runs correctly and serves swagger properly."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "Swagger UI" in response.text


def test_openapi_schema_generation():
    """Tests If FastAPI correctly generates OpenAPI schema."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/auth" in schema["paths"]
    assert "/projects" in schema["paths"]


def test_unauthorized_access_is_blocked():
    """Tests If unauthorized access is blocked (code 401)."""
    response = client.get("/projects")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_user_registration_success():
    """Tests successful user registration with mocked DB."""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "550e8400-e29b-41d4-a716-446655440000"

    async def override_get_db():
        yield mock_conn

    app.dependency_overrides[get_db_connection] = override_get_db

    payload = {
        "login": "testuser",
        "password": "testpassword123",
        "repeat_password": "testpassword123",
    }
    response = client.post("/auth", json=payload)

    assert response.status_code == 201
    assert response.json()["message"] == "User created succesfully"
    assert "user_id" in response.json()

    app.dependency_overrides.clear()


def test_login_success():
    """Tests successful login with mocked DB."""
    mock_conn = AsyncMock()
    from src.core.security import get_password_hash

    hashed = get_password_hash("testpassword123")

    mock_conn.fetchrow.return_value = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "password_hash": hashed,
    }

    async def override_get_db():
        yield mock_conn

    app.dependency_overrides[get_db_connection] = override_get_db

    response = client.post(
        "/login", data={"username": "testuser", "password": "testpassword123"}
    )

    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"

    app.dependency_overrides.clear()


def test_create_project_success():
    """Tests successful project creation with mocked DB and Auth."""
    from src.api.deps import get_current_user

    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "550e8400-e29b-41d4-a716-446655440001"

    from unittest.mock import MagicMock

    mock_transaction_cm = MagicMock()
    mock_transaction_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_transaction_cm.__aexit__ = AsyncMock(return_value=None)

    mock_conn.transaction.return_value = mock_transaction_cm

    mock_conn.transaction = MagicMock(return_value=mock_transaction_cm)

    async def override_get_db():
        yield mock_conn

    async def override_get_current_user():
        return "550e8400-e29b-41d4-a716-446655440000"

    app.dependency_overrides[get_db_connection] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    payload = {"name": "New Project", "description": "Project description"}

    response = client.post(
        "/projects", json=payload, headers={"Authorization": "Bearer fake-token"}
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Project created successfully"
    assert "project_id" in response.json()

    app.dependency_overrides.clear()


def test_get_projects_includes_documents():
    """Tests if GET /projects returns documents list."""
    from src.api.deps import get_current_user
    from unittest.mock import AsyncMock

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "name": "Project 1",
            "description": "Desc 1",
            "total_storage_bytes": 100,
            "documents": [
                {
                    "id": "550e8400-e29b-41d4-a716-44665544000a",
                    "project_id": "550e8400-e29b-41d4-a716-446655440001",
                    "filename": "file.pdf",
                    "s3_key": "key/file.pdf",
                    "size_bytes": 50,
                    "created_at": "2024-01-01T00:00:00Z"
                }
            ]
        }
    ]

    async def override_get_db():
        yield mock_conn

    async def override_get_current_user():
        return "550e8400-e29b-41d4-a716-446655440000"

    app.dependency_overrides[get_db_connection] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.get("/projects", headers={"Authorization": "Bearer fake-token"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "documents" in data[0]
    assert len(data[0]["documents"]) == 1
    assert data[0]["documents"][0]["filename"] == "file.pdf"

    app.dependency_overrides.clear()


def test_create_document_path_updated():
    """Tests if a POST /project/{id}/documents path works."""
    from src.api.deps import get_current_user
    from unittest.mock import AsyncMock, patch

    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "owner"

    async def override_get_db():
        yield mock_conn

    async def override_get_current_user():
        return "550e8400-e29b-41d4-a716-446655440000"

    app.dependency_overrides[get_db_connection] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    project_id = "550e8400-e29b-41d4-a716-446655440001"
    payload = {"filename": "test.txt", "content_type": "text/plain"}

    with patch("src.api.documents.generate_presigned_upload_url", new_callable=AsyncMock) as mock_s3:
        mock_s3.return_value = "http://fake-s3-url.com"
        response = client.post(
            f"/project/{project_id}/documents",
            json=payload,
            headers={"Authorization": "Bearer fake-token"}
        )

    assert response.status_code == 201
    assert "upload_url" in response.json()
    assert response.json()["upload_url"] == "http://fake-s3-url.com"

    app.dependency_overrides.clear()
