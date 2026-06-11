from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine
from app.api import auth, push, logs, clients, admin, dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables on startup (use Alembic for production migrations)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Limpid IT — Log Console API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(push.router, prefix="/api")   # /api/log  /api/logs/batch
app.include_router(logs.router, prefix="/api")   # /api/logs  /api/logs/sessions
app.include_router(clients.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
