from contextlib import asynccontextmanager

import asyncpg
from fastapi import Depends, FastAPI

from src.api import auth, documents, projects
from src.core.config import settings
from src.db.connection import close_db_connection, connect_to_db, get_db_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_db()
    yield
    await close_db_connection()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(projects.join_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/health")
async def health_check(conn: asyncpg.Connection = Depends(get_db_connection)):
    result = await conn.fetchval("SELECT NOW()")
    return {"status": "ok", "db_time": result}
