from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.database import Base, engine
from app.api import auth, push, logs, clients, admin, dashboard


def _get_api_key_or_ip(request: Request) -> str:
    """Rate limit push endpoints by API key, everything else by IP."""
    return request.headers.get("X-API-Key") or get_remote_address(request)


limiter = Limiter(key_func=get_remote_address, default_limits=[])

# Make limiter available to route decorators via app.state
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Limpid IT — Log Console API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://limpid-log-console.pages.dev",
        "http://localhost:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(push.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(clients.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
