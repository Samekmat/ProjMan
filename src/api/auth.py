import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from src.api.deps import get_current_user
from src.api.schemas import TokenResponse, UserCreate
from src.core.security import create_access_token, get_password_hash, verify_password
from src.db.connection import get_db_connection

router = APIRouter(tags=["Authentication"])


@router.post("/auth", status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreate, conn: asyncpg.Connection = Depends(get_db_connection)
):
    if user.password != user.repeat_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords don't match"
        )
    hashed_password = get_password_hash(user.password)

    try:
        user_id = await conn.fetchval(
            """
            INSERT INTO users (login, password_hash)
            VALUES ($1, $2)
            RETURNING id
            """,
            user.login,
            hashed_password,
        )
        return {"message": "User created succesfully", "user_id": user_id}

    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this login already exists",
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    conn: asyncpg.Connection = Depends(get_db_connection),
):

    db_user = await conn.fetchrow(
        "SELECT id, password_hash FROM users WHERE login = $1", form_data.username
    )

    if not db_user or not verify_password(form_data.password, db_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(db_user["id"])})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(current_user_id: str = Depends(get_current_user)):
    """Return current user id"""
    return {"my_user_id": current_user_id, "message": "You are logged in!"}
