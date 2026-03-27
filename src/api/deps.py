import asyncpg
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from src.core.config import settings
from src.db.connection import get_db_connection

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> str:
    """
    Dependency Injection: Verifies JWT token and returns user ID.
    If token is not valid, raise error
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user_record = await conn.fetchrow(
        "SELECT id FROM users WHERE id = $1::uuid", user_id
    )

    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")

    return str(user_record["id"])
