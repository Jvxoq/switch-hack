---
name: fastapi
description: "Use whenever writing, reviewing, or refactoring FastAPI/Python backend code — new endpoints, use cases, repositories, database access, LLM or vector-store calls, background jobs, auth, streaming, or project structure decisions. Load BEFORE writing code, not after review finds problems. Encodes agent discipline, current library APIs (Pydantic v2, SQLAlchemy 2.0, lifespan), the dependency rule (domain ← application ← adapters/api, wired at one composition root), async and blocking rules, race conditions, Postgres and migration safety, API contracts, retries, security, scale (pooling, caching, sharding, backpressure), observability, testing, tooling, and safe deploys. Includes an audit mode for finding violations in existing backends."
---

# FastAPI — production backend rules

FastAPI is a delivery mechanism, not an architecture. This skill exists so layering violations are
prevented while writing, and caught mechanically when prevention fails.

Sections 1 to 14 are rules to apply while writing. §15 audits code that already exists.

---

## 1. Agent discipline

These stop the mistakes that only an AI makes.

- Read the code around the change first, and copy its patterns.
- Check the installed version in uv.lock before you use a library. Never guess an API.
- Never leave a stub, a TODO or a pass and call the work done.
- Never edit or skip a test to make it pass. Fix the code.
- Make the smallest change that works. No renames or refactors on the side.
- Delete any code your change leaves unused.
- Run the tests, ruff and mypy, and show the output before you say done.
- Never invent a setting, an env var or a file path. Search the repo for it first.
- Ask before you add a dependency. Check the standard library and the current dependencies first.
- Never claim a speed you did not measure. "Handles high load" needs a load test number.

## 2. Current APIs, not old ones

Models learn from old code, so they write old code.

- Pydantic v2 uses `model_config`, `field_validator` and `model_dump()`. Never `class Config`, `@validator` or `.dict()`.
- Pydantic v2 also uses `model_validate()`, `model_dump_json()` and `from_attributes=True`. Never `parse_obj()`, `.json()` or `orm_mode`.
- Import `BaseSettings` from `pydantic_settings`. It moved out of `pydantic` in v2.
- Use `lifespan`, the app's startup and shutdown hook. Never `@app.on_event`.
- SQLAlchemy 2.0 uses `select()`, `Mapped[]` and `mapped_column()`. Never `session.query()`.
- Async SQLAlchemy uses `create_async_engine`, `async_sessionmaker` and `DeclarativeBase`. Never `declarative_base()`.
- Write dependencies as `Annotated[X, Depends(f)]`. Never `x: X = Depends(f)`.
- Use `httpx.AsyncClient` for HTTP. Never `requests`.
- Use `redis.asyncio` for Redis. The `aioredis` package is dead.
- Use PyJWT for tokens and argon2-cffi for passwords. Never python-jose or passlib. Both went years without updates.
- Use `datetime.now(UTC)`. Never `datetime.utcnow()`, because it returns a time with no zone.
- Use `asyncio.get_running_loop()` and `asyncio.timeout()`. Never `asyncio.get_event_loop()`.
- Write `X | None` and `list[str]`. Never `Optional[X]` or `List[str]`.

## 3. Architecture

- Imports point inward: API and adapters, then application, then domain.
- A router parses the request, calls one use case and returns the response. Nothing else.
- A use case is one class that runs one business action. All logic lives there.
- A `Depends` function only returns an object. It holds no logic.
- Importing a module never opens a connection. `lifespan` builds every client.
- One file reads environment variables. Everything else receives values as arguments.
- A use case receives its collaborators as ports, which are `Protocol` interfaces.
- Settings load and validate in `lifespan`. A missing variable stops the boot, not the first request.

The subsections below show how each rule looks in code.

### 3.1 The dependency rule

Every rule below follows from this one. Imports point inward, always:

```
domain/         imports stdlib only
application/    imports domain
adapters/       imports application + domain      (implements application's ports)
api/            imports application + domain      (never adapters)
composition.py  imports everything                (the only module allowed to)
```

An arrow pointing the wrong way is a defect, not a style preference. §13 makes it fail CI.

### 3.2 Non-negotiables

Each is a prohibition paired with its replacement. When a rule seems to block you, the answer is
almost always that a use case is missing.

1. **No logic in `Depends`.** A dependency function resolves an object and returns it. Branching,
   I/O, prompt building, retrieval, orchestration → a use case.
2. **Compose, never inherit, your adapters.** `class Service(Repository)` welds the use case to one
   database. Dependencies arrive as constructor arguments typed as `Protocol` ports.
3. **No infrastructure at import time.** Zero module-level engines, clients, sessions, or pools.
   Importing a module must never open a socket. Construction happens in `lifespan`, nowhere else.
4. **Settings are read once and injected.** Only `settings.py` and `composition.py` touch config. A
   layer that imports settings has smuggled the composition root into itself.
5. **DTOs live in the layer that owns the contract.** HTTP shapes in `api/schemas/`, use case
   inputs/outputs in `application/`. Never in `adapters/` or `infrastructure/`.
6. **The domain is framework-free.** Entities are `dataclasses`. No FastAPI, no SQLAlchemy, no
   Pydantic below `application/`. If nothing survives deleting FastAPI, there is no domain layer.
7. **No `utils.py`, `helpers.py`, `common.py`.** Every module names one capability. An LLM streaming
   helper and a file-saving helper are two adapters, not one grab-bag.
8. **`main.py` only builds the app.** No routes, no handlers, no logic. Route bodies never reach
   into `app.state` — that is what dependencies are for.
9. **One organizing axis, held consistently.** Layer-first by default. Feature-first is legitimate
   *only* if each feature folder separates layers internally and the dependency rule still holds. A
   folder with `extractor.py`, `transformer.py`, `repository.py`, `service.py` as flat peers is not
   a feature — it is four layers with the boundaries erased.

### 3.3 Where does this code go?

Consult before writing, not after.

| The code… | Goes in | Note |
|---|---|---|
| Enforces a business rule, no I/O | `domain/<ctx>/entities.py` | Methods on entities |
| A concept with no identity (Money, Email) | `domain/<ctx>/value_objects.py` | Frozen dataclass |
| Names a business failure | `domain/<ctx>/errors.py` | Plain exception, no HTTP status |
| Orchestrates ≥2 collaborators for one request | `application/<ctx>/use_cases/` | One per use case |
| Declares what a use case needs from outside | `application/<ctx>/ports.py` | `typing.Protocol` |
| A use case's input/output shape | `application/<ctx>/dto.py` | Owned by app, not wire |
| Talks to Postgres/Qdrant/Groq/S3/any HTTP API | `adapters/<kind>/` | Implements a port |
| Translates a domain object to/from a DB row | `adapters/persistence/mappers.py` | ORM stays here |
| Defines an HTTP request/response body | `api/v1/schemas/` | Pydantic; wire contract only |
| Handles a route | `api/v1/routers/` | Parse → call use case → serialize |
| Maps a domain error to a status code | `api/errors.py` | Only place status codes appear |
| Lists the use cases the API can call | `api/container.py` | `AppContainer`, filled by `lifespan` |
| Constructs a client, engine, or pool | `composition.py` | Only place, inside `lifespan` |
| Reads an environment variable | `settings.py` | Only place |

**The one sanctioned shortcut:** a pure passthrough read (`GET` → repository → serialize, no policy,
no second collaborator, no transaction) may call the repository port straight from the router. The
moment a decision, policy, second collaborator, or write transaction appears, it becomes a use case.
Do not generalize this into "simple things skip the layer."

### 3.4 Canonical layout

```
src/app/
├── main.py               # create_app() and nothing else
├── settings.py           # pydantic-settings; only reader of the environment
├── composition.py        # lifespan: loads settings, builds every client, fills AppContainer
├── domain/<ctx>/         # entities.py  value_objects.py  errors.py
├── application/
│   ├── <ctx>/            # ports.py  dto.py  use_cases/
│   └── common/           # uow.py  clock.py  principal.py
├── adapters/
│   ├── persistence/      # models.py  mappers.py  repositories.py  uow.py
│   ├── clock.py          # SystemClock, the real Clock
│   └── llm/  vector/  http/  storage/
├── api/
│   ├── v1/routers/  v1/schemas/
│   ├── container.py      # AppContainer: the use cases the API can call
│   ├── dependencies.py   # container lookups only, zero logic
│   ├── auth.py           # authenticate: bearer token → Principal
│   ├── health.py         # /health and /ready, public on purpose
│   ├── errors.py         # domain error → HTTP status
│   └── middleware/       # plain ASGI middleware only
└── observability/        # logging setup, correlation-ID contextvar
```

`<ctx>` is a bounded context (`billing`, `ingestion`, `chat`) — not a technical grouping
(`services`, `managers`) and not a table name. Start with one; split when the language diverges, not
when the file gets long.

### 3.5 Composition root

#### Settings — read once

```python
# app/settings.py
from pydantic import AnyHttpUrl, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    environment: str = "local"
    database_url: PostgresDsn
    database_pool_size: int = 10
    database_pool_timeout_seconds: float = 5.0
    qdrant_url: AnyHttpUrl
    qdrant_api_key: SecretStr
    request_timeout_seconds: float = 30.0
```

`extra="forbid"` turns a typo'd env var into a startup crash instead of a silent default.
`SecretStr` keeps credentials out of logs and tracebacks. **`lifespan` builds `Settings()` once, so
a missing variable stops the boot, not the first request.** There is no `get_settings()` accessor.
A second way to reach settings is how other layers start reading config on their own.

#### Container + lifespan

```python
# app/api/container.py
from dataclasses import dataclass

from app.application.ingestion.use_cases.ingest_document import IngestDocument


@dataclass(frozen=True, slots=True)
class AppContainer:
    ingest_document: IngestDocument
    # one field per use case the API can invoke
```

```python
# app/composition.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.adapters.clock import SystemClock
from app.adapters.persistence.uow import SqlAlchemyUnitOfWork
from app.adapters.vector.qdrant_index import QdrantVectorIndex
from app.api.container import AppContainer
from app.application.ingestion.use_cases.ingest_document import IngestDocument
from app.observability.logging import configure_logging
from app.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()  # type: ignore[call-arg]  # required fields come from the environment
    configure_logging(settings)

    engine: AsyncEngine = create_async_engine(
        str(settings.database_url),
        pool_size=settings.database_pool_size,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    index = QdrantVectorIndex(
        url=str(settings.qdrant_url),
        api_key=settings.qdrant_api_key.get_secret_value(),
        timeout=settings.request_timeout_seconds,
    )

    app.state.container = AppContainer(
        ingest_document=IngestDocument(
            new_uow=partial(SqlAlchemyUnitOfWork, session_factory),
            index=index,
            clock=SystemClock(),
        ),
    )
    try:
        yield
    finally:
        await index.aclose()
        await engine.dispose()
```

The `finally` block is not optional — without it, redeploys leak connections until the database
refuses new ones.

`AppContainer` lives in `api/`, not here. The API layer must never import `composition.py`, because
that module imports every adapter (§13).

#### `main.py` — the whole file

```python
# app/main.py
from fastapi import APIRouter, Depends, FastAPI

from app.api import health
from app.api.auth import authenticate
from app.api.errors import register_exception_handlers
from app.api.middleware.correlation import CorrelationIdMiddleware
from app.api.v1.routers import ingestion
from app.composition import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title="…", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    authenticated = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])
    authenticated.include_router(ingestion.router)
    app.include_router(authenticated)
    app.include_router(health.router)
    return app


app = create_app()
```

A factory (not module-level `app = FastAPI()` with decorators) is what lets tests build an app with
a substituted container. Every versioned router mounts under `authenticated`, so auth is the default
(§9). A route is public only when it is mounted outside it on purpose, like `health`.

#### Dependencies — resolution only

```python
# app/api/dependencies.py
from typing import Annotated
from fastapi import Depends, Request

from app.api.container import AppContainer
from app.application.ingestion.use_cases.ingest_document import IngestDocument


async def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


async def get_ingest_document(
    container: Annotated[AppContainer, Depends(get_container)],
) -> IngestDocument:
    return container.ingest_document


IngestDocumentDep = Annotated[IngestDocument, Depends(get_ingest_document)]
```

Every function is one lookup and one `return`. A branch, an `await` on a client, or a query here
means the logic belongs in a use case. They are `async def` because a plain `def` dependency runs in
the thread pool (§4).

**The two legitimate exceptions**, because they are delivery concerns: **authentication** (decoding a
bearer token into a principal — the *authorization decision* still belongs in the use case), and
**request-scoped context** (correlation ID, tenant, pagination params). Everything else is a use case
in a `Depends` costume.

### 3.6 Domain

```python
# app/domain/ingestion/entities.py
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.ingestion.errors import DocumentAlreadyIndexed


@dataclass(slots=True)
class Document:
    id: UUID
    source_url: str
    content: str
    indexed_at: datetime | None = None
    chunks: list[str] = field(default_factory=list)

    def mark_indexed(self, at: datetime) -> None:
        if self.indexed_at is not None:
            raise DocumentAlreadyIndexed(self.id)
        self.indexed_at = at

    def is_indexable(self) -> bool:
        return bool(self.content.strip())
```

- Stdlib `dataclasses`, not Pydantic. Pydantic is validation/serialization; letting it in drags wire
  concerns inward, and the ban is mechanically checkable.
- Value objects are `@dataclass(frozen=True)` validating in `__post_init__`.
- Domain errors are plain exceptions carrying business facts — never an HTTP status.
- **Avoid an anemic domain.** Rules depending only on the object's own state live on the entity
  (`Order.total()`, `Subscription.is_expired(now)`). Rules needing collaborators or I/O live in a use
  case. If a use case reaches through attributes to compute what the entity could compute itself,
  move it down.

### 3.7 Application — ports, use cases, transactions

```python
# app/application/ingestion/ports.py
from typing import Protocol
from uuid import UUID
from app.domain.ingestion.entities import Document


class DocumentRepository(Protocol):
    async def get(self, document_id: UUID) -> Document | None: ...
    async def add(self, document: Document) -> None: ...


class VectorIndex(Protocol):
    async def upsert(self, document_id: UUID, chunks: list[str]) -> None: ...
    async def search(self, query: str, limit: int) -> list[str]: ...
```

`Protocol`, not ABC: structural typing means adapters neither inherit from nor import the port. That
is the cleanest seam available, and it is what kills "service inherits its adapter."

```python
# app/application/common/uow.py
from typing import Protocol, Self
from app.application.ingestion.ports import DocumentRepository


class UnitOfWork(Protocol):
    documents: DocumentRepository

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

```python
# app/application/common/clock.py
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
```

```python
# app/application/ingestion/use_cases/ingest_document.py
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid7  # uuid7 is in the stdlib from Python 3.14

from app.application.common.clock import Clock
from app.application.common.uow import UnitOfWork
from app.application.ingestion.ports import VectorIndex
from app.domain.ingestion.entities import Document
from app.domain.ingestion.errors import DocumentNotIndexable


@dataclass(frozen=True, slots=True)
class IngestDocumentInput:
    source_url: str
    content: str


@dataclass(frozen=True, slots=True)
class IngestDocumentResult:
    document_id: UUID


class IngestDocument:
    def __init__(
        self, new_uow: Callable[[], UnitOfWork], index: VectorIndex, clock: Clock
    ) -> None:
        self._new_uow = new_uow
        self._index = index
        self._clock = clock

    async def __call__(self, data: IngestDocumentInput) -> IngestDocumentResult:
        document = Document(id=uuid7(), source_url=data.source_url, content=data.content)
        if not document.is_indexable():
            raise DocumentNotIndexable(document.source_url)

        document.chunks = chunk(document.content)
        await self._index.upsert(document.id, document.chunks)
        document.mark_indexed(self._clock.now())

        async with self._new_uow() as uow:
            await uow.documents.add(document)
            await uow.commit()

        return IngestDocumentResult(document_id=document.id)
```

- Collaborators arrive in `__init__`, typed as ports. The use case never names Qdrant or Postgres.
- **One use case object serves every request.** So it takes a UoW factory and opens a fresh UoW on
  each call. A UoW stored on `self` would share one session across concurrent requests (§5).
- The clock is a port too. Tests pass a fixed clock instead of patching `datetime` (§12).
- **The use case owns the transaction boundary** — not the repository, and never a session opened in
  a `Depends` and passed down.
- Keep non-transactional I/O (the vector upsert) outside the `async with` so a slow network call does
  not hold a database transaction open.
- One use case per file, named as an action.

### 3.8 Adapters

```python
# app/adapters/persistence/repositories.py
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence import models
from app.adapters.persistence.mappers import to_domain, to_model
from app.domain.ingestion.entities import Document


class SqlAlchemyDocumentRepository:  # satisfies DocumentRepository structurally
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, document_id: UUID) -> Document | None:
        row = await self._session.get(models.Document, document_id)
        return to_domain(row) if row else None

    async def add(self, document: Document) -> None:
        self._session.add(to_model(document))
```

```python
# app/adapters/clock.py
from datetime import UTC, datetime


class SystemClock:  # satisfies Clock structurally
    def now(self) -> datetime:
        return datetime.now(UTC)
```

- ORM models are **adapter types**, not domain entities. `mappers.py` translates between them. This
  is the boundary that keeps lazy loading, session identity, and migrations out of the domain.
- Repositories do not commit — the UoW does.
- Repositories return domain objects, never ORM rows, and never `Result` objects.
- External-service adapters (LLM, vector, HTTP, storage) follow the same shape: constructor takes
  already-configured clients, methods speak domain/application types, and **every outbound call has
  an explicit timeout**. Translate vendor exceptions into application-level errors at this boundary
  so retry policy and failure handling do not leak upward.
- Give each adapter an `aclose()` and call it in the `lifespan` `finally`.

### 3.9 API layer

```python
# app/api/v1/routers/ingestion.py
from fastapi import APIRouter, status

from app.api.dependencies import IngestDocumentDep
from app.api.v1.schemas.ingestion import IngestRequest, IngestResponse
from app.application.ingestion.use_cases.ingest_document import IngestDocumentInput

router = APIRouter(tags=["ingestion"])


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def ingest_document(
    body: IngestRequest, use_case: IngestDocumentDep
) -> IngestResponse:
    result = await use_case(
        IngestDocumentInput(source_url=str(body.source_url), content=body.content)
    )
    return IngestResponse(document_id=result.document_id)
```

Parse, call, serialize. Nothing else — no matter how few lines the "else" would be.

```python
# app/api/errors.py
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.domain.ingestion.errors import DocumentAlreadyIndexed, DocumentNotIndexable
from app.observability.context import correlation_id

_STATUS: dict[type[Exception], int] = {
    DocumentNotIndexable: status.HTTP_422_UNPROCESSABLE_ENTITY,
    DocumentAlreadyIndexed: status.HTTP_409_CONFLICT,
}


def _error_response(code: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={
            "error": {
                "type": error_type,
                "message": message,
                "correlation_id": correlation_id.get(),
            }
        },
    )


async def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(_STATUS[type(exc)], type(exc).__name__, str(exc))


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.opt(exception=exc).error("unhandled error")
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "InternalServerError", "Internal server error"
    )


def register_exception_handlers(app: FastAPI) -> None:
    for error_type in _STATUS:
        app.add_exception_handler(error_type, _handle_domain_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
```

The single place domain failures become HTTP. Use cases raise domain errors; they never import
`HTTPException`. 5xx responses never echo the exception message — that is how internals and
connection strings leak.

Each domain error gets its own handler. Starlette sends an `Exception` handler to its outer error
middleware, which re-raises after responding, so a catch-all would log every 4xx as a crash. Register
`RequestValidationError` and Starlette's `HTTPException` the same way, so FastAPI's own 422 and 404
use this one error shape too.

**Other API-layer rules:**
- Response models are explicit return annotations, so OpenAPI and mypy agree.
- **Streaming/SSE:** yield from a use case that returns an `AsyncIterator`; the router only formats
  frames. Build the prompt, choose the model, and assemble context in the use case — not in the
  generator, and not in a dependency.
- The wire contract rules are in §7.

## 4. Async and blocking

The event loop is the one thread that runs all async code. One blocking call freezes every request.

- No blocking call inside `async def`. That means no `requests`, `time.sleep`, sync database driver or large file read.
- Hidden blocking calls count too. Examples are DNS lookup, password hashing, a large `json.loads` and pandas.
- Sync SDKs block too. Examples are boto3, the sync OpenAI client and the sync redis client.
- Log writes block when the log pipe is full. Send logs through a queue, for example loguru's `enqueue=True`.
- Blocking input and output goes to `asyncio.to_thread`. Heavy CPU work goes to a process pool or a worker.
- A `def` route runs in a thread pool of 40 threads. A few slow sync routes use it all up.
- A `def` dependency runs in that same pool. Make every cheap dependency `async def`.
- Write middleware as plain ASGI middleware. `BaseHTTPMiddleware` adds cost to every request and has contextvar limits.
- Every network call has a timeout, read from settings.
- `lifespan` builds one shared client per service. A new client per request loses connection reuse.
- A semaphore sized from settings bounds every fan-out.
- Use `asyncio.TaskGroup` for fan-out. Keep a reference to every `create_task` result, or Python can delete the task mid-run.
- Never swallow `CancelledError`. Clean up, then let it rise.
- `BackgroundTasks` runs in the same process after the response. A restart loses that work. Use it only for work you can lose.
- Tests fail on any blocking call. The blockbuster library does this.

## 5. Race conditions

- No module-level dict, list or counter that requests change. Each worker process has its own copy anyway.
- Request data lives in arguments or a contextvar, a variable asyncio keeps separate per request. Never in a global or a class attribute.
- Never change a shared client inside a request. A header set on the shared httpx client leaks one user's token into another user's request.
- Other requests run at every `await`. A value you read before an `await` may be stale after it.
- Check-then-act is a race. "If it does not exist, insert it" fails under load. Use a unique constraint and `INSERT ... ON CONFLICT`.
- Read-modify-write is a race. "Read the balance, change it, save it" loses updates. Use one atomic `UPDATE ... SET x = x - :n`.
- When you must read then write, lock the row with `SELECT ... FOR UPDATE`. Or add a version column and fail if it changed. That is optimistic locking.
- Lock rows in one fixed order, for example by ID. Two transactions that lock in opposite order wait on each other forever. That is a deadlock.
- Retry a transaction that fails with a deadlock or a serialization error. Postgres expects the client to retry these two.
- `asyncio.Lock` works inside one process only. Across workers, lock in the database or Redis.
- A Redis lock needs a TTL and a random token. Only the token holder may release it. It can still expire mid-work. So it saves effort but never guards correctness.
- Every write a client may retry takes an idempotency key. Save the key under a unique constraint, in the same transaction as the write. A repeat gets the saved response.
- Each unit of work gets its own database session. Never share a session across concurrent tasks.
- A queue can deliver a message twice. Every job handler must be safe to run twice.
- Messages and webhooks arrive out of order. Store a version number and ignore anything older.
- Never order events by clocks from different machines. The clocks disagree. Use the database clock or a sequence.
- A database write plus a message send can half-fail. Save the message in the same transaction and send it later. That is the outbox pattern.
- Update the database, then delete the cache key. The reverse order lets a slow reader put old data back.
- A replica can run behind the primary. That is replication lag. Read your own fresh writes from the primary.

## 6. Database

- Use parameterized queries only. Never build SQL with an f-string.
- No N+1 queries, meaning one extra query per row in a loop. Load related rows with `selectinload`.
- Async SQLAlchemy cannot lazy-load. Touching an unloaded relation raises `MissingGreenlet`.
- Build async sessions with `expire_on_commit=False`. Otherwise commit marks every field stale. The next read then raises `MissingGreenlet`.
- Keep transactions short. Never call the network inside one.
- A session holds its connection until commit or close. Commit before any slow call, or slow calls empty the pool.
- Set `statement_timeout` and `lock_timeout` on the database role. They stop a slow query and a query stuck waiting for a lock.
- Set a pool checkout timeout. A request that cannot get a connection fails fast instead of hanging.
- Put rules in the database too: `UNIQUE`, `NOT NULL`, foreign keys and `CHECK`.
- Index every column that hot queries filter, join or sort on.
- Every list query has a limit with a maximum. Use keyset pagination, meaning "rows after this ID", not `OFFSET`.
- Never return a total count on a large list. `COUNT(*)` scans every matching row.
- Use UUIDv7 for IDs, a UUID that sorts by time. Random UUIDv4 scatters index writes. A plain counter lets clients guess IDs.
- Pool size times workers times servers stays under PgBouncer's client limit. PgBouncer's own pool stays under Postgres `max_connections`.
- PgBouncer in transaction mode gives each transaction any free connection. That breaks `SET`, `LISTEN`, session advisory locks and prepared statements. For asyncpg, turn off its statement cache.
- Store time as `timestamptz` in UTC. Store money as `Decimal` or integer cents, never float.
- Migrations run as a separate step, never at app start. Read every autogenerated migration.
- Change a schema in steps: add the new column, deploy, backfill, then drop the old one. That is expand and contract. Old and new code run side by side during a deploy.
- Build indexes with `CREATE INDEX CONCURRENTLY`. A plain `CREATE INDEX` blocks writes to the table.
- Every migration sets `lock_timeout`. A migration waiting for a lock blocks every query behind it.
- Insert many rows in one statement or with `COPY`, the Postgres bulk load command. Never one `INSERT` per row.

## 7. API contract

- Request and response schemas are separate Pydantic models. Never return an ORM row or a domain object.
- Request models use `extra="forbid"`. Every string, list and number has a size limit.
- Never copy a request straight into a database row. A client could set `is_admin`. That is mass assignment.
- Use the right status code: 201 created, 204 no content, 404 not found, 409 conflict, 422 bad input.
- Never return 200 with an error inside the body.
- Every error response uses one shape.
- Version the API.
- Never add a required field to an existing request. It breaks every current client.
- Never remove or rename a response field. Add a new field instead.
- FastAPI sets no limit on request body size. Set one in the proxy, or one huge body fills a worker's memory.
- Cacheable `GET` responses send `Cache-Control`, which says how long to keep them. Add `ETag`, a version tag, so repeat requests get a cheap 304.

## 8. Errors and retries

- One file turns domain errors into HTTP codes.
- No bare `except`. Log with `logger.exception`, then re-raise or return a value the caller can tell apart from success.
- A 5xx response never shows internals. It returns a plain message and the correlation ID.
- Retry only transient errors, and only operations that are safe to repeat.
- Use exponential backoff, where each wait doubles. Add jitter, a random extra wait, so clients do not retry together. Honour `Retry-After`.
- Every retry loop has a ceiling on total wait time.
- Retry at one layer only. Three layers that each try three times make 27 calls for one request.
- Cap retries at about 10 percent of traffic. That is a retry budget. Without it, retries turn a slowdown into an outage.
- Put a circuit breaker on each dependency. It stops calls to a failing service and fails fast until the service recovers.
- Give each request a deadline. Pass the time left to every downstream call, and stop when it runs out.
- One failed item in a batch fills its own slot with an error. The batch still returns.

## 9. Security

- A dependency decodes the token. That is authentication. The use case decides what the user may do. That is authorization.
- Every router requires auth by default. A public route opts out on purpose. A new endpoint never ships open by accident.
- Check that the record belongs to the caller. Otherwise a user can read another user's data by changing an ID.
- Secrets use `SecretStr`, come from the environment and never reach a log.
- Compare secrets with `hmac.compare_digest`, never `==`.
- Hash passwords with argon2 or bcrypt inside `asyncio.to_thread`.
- Verify the JWT signature, pin the algorithm and check expiry.
- A server that fetches a user-given URL refuses private and local addresses. That blocks SSRF, where a caller makes your server call internal hosts.
- Uploads have a size limit. Never use the client's filename as a file path.
- Never `pickle.loads` or `yaml.load` untrusted input.
- CORS lists exact origins. Rate-limit login and expensive endpoints per user.
- Trust `X-Forwarded-For` only from your own proxy. Otherwise a client fakes its IP and escapes the rate limit.

The PyJWT call inside `authenticate`:

```python
claims = jwt.decode(
    token,
    public_key,
    algorithms=["RS256"],                 # pinned; never taken from the token header
    options={"require": ["exp", "sub"]},  # a token with no expiry is refused
)
```

## 10. Scale

- One Python process serves about 1,000 to 5,000 requests per second. 20 million needs thousands of processes. At that size the database and cache break first, not Python.
- The cheapest request never reaches Python. Serve cacheable responses from a CDN, a cache close to the user.
- Every worker is stateless. Sessions, caches and locks live in Redis or the database.
- Run several worker processes per server, about one per CPU core.
- In a container, set the worker count from the CPU limit. `os.cpu_count()` returns the host's cores and starts too many workers.
- Put a connection pooler like PgBouncer in front of Postgres.
- One Postgres primary cannot take this load. Send reads to replicas.
- Split data across databases by one key, for example the tenant ID. That is sharding. Every hot query includes that key. No transaction crosses two shards.
- Cache hot reads in Redis with a TTL, a time after which the entry expires.
- Add random jitter to every TTL. Keys written together must not expire together.
- Stop many requests from rebuilding one expired key at once. That problem is a cache stampede.
- Cache "not found" too, with a short TTL. Otherwise requests for missing IDs all reach the database.
- A hot key is one key that most requests read. It overloads one shard. Keep a short-lived in-process copy of it.
- Split a hot counter into many rows and sum them on read. One row that every request updates makes all writes wait in line.
- In Redis Cluster, a command with many keys fails unless the keys share a hash tag. A hash tag is the `{part}` of a key that picks the node.
- Every in-process cache has a max size and a TTL. An unbounded `lru_cache` is a memory leak.
- Apply backpressure. Cap in-flight requests per worker, for example with uvicorn's `--limit-concurrency`. Return 429 or 503 fast. Never queue forever.
- Slow work goes to a durable queue. The endpoint returns 202 with a job ID.
- Stream large responses. Never load a whole file into memory.
- Prove the number with a load test in k6 or Locust. Measure p99 latency, the time 99 percent of requests beat.

## 11. Observability

- Write structured JSON logs with a correlation ID, one ID that follows a request everywhere.
- Never log secrets, full bodies or personal data. Log a length and a hash.
- Track per route: request rate, error rate and p99 latency.
- Label metrics with the route template, like `/users/{id}`. Never the raw path or a user ID. Each unique value makes a new series and overloads the metrics store.
- Track saturation, meaning how full each resource is. Watch pool wait time, thread pool use and event loop lag, meaning how late the loop runs its work. Loop lag is how you catch a blocking call in production.
- Send OpenTelemetry traces across services.
- Sample traces and high-volume logs. Recording every request at this scale costs more than serving it.
- `/health` returns a static 200. `/ready` checks only this process: startup finished and not draining. If `/ready` checks the shared database, one database blip pulls every server out of the load balancer.
- On shutdown, the `lifespan` `finally` block closes every client.

The correlation ID as plain ASGI middleware and a contextvar:

```python
# app/observability/context.py
from contextvars import ContextVar

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
```

```python
# app/api/middleware/correlation.py
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.context import correlation_id


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = uuid4().hex
        # No reset: each request runs in its own task, and the 500 handler
        # runs outside this middleware and still needs the ID.
        correlation_id.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                MutableHeaders(scope=message).append("x-request-id", request_id)
            await send(message)

        await self._app(scope, receive, send_with_id)
```

## 12. Testing

- Use case tests use fakes, meaning small in-memory versions of a port. Not mocks.
- Each fake passes the same contract tests as the real adapter. Otherwise the fake drifts, and tests pass against behavior that does not exist.
- Adapter tests run against real Postgres in testcontainers.
- Never test with SQLite when production runs Postgres. Locking, types and SQL features behave differently.
- API tests use `httpx.ASGITransport` with a swapped container. It does not run `lifespan`, so set the container yourself.
- Tests use no network and no real clock. Inject the clock.
- Test each race against real Postgres, with separate sessions running at once. Fakes and one shared session never show the race.
- Test the failure paths: timeout, upstream 500 and duplicate request.
- CI runs every migration against a real database.
- One behaviour per test. Assert what happened, not that a mock was called.

Swap the container, not the world:

```python
@pytest.fixture
def app_with(container: AppContainer, principal: Principal) -> FastAPI:
    app = create_app()
    app.state.container = container  # ASGITransport skips lifespan, so set it here

    async def as_principal() -> Principal:
        return principal

    app.dependency_overrides[authenticate] = as_principal
    return app
```

## 13. Types and tooling

- `mypy --strict` passes. No bare `dict` or `list`. No `Any` outside a decoding boundary.
- ruff runs with the `ASYNC`, `S` and `B` rule families.
- import-linter fails the build when an import points the wrong way.
- No `utils.py` or `helpers.py`. Each module names one job.
- Dependencies go through uv and `pyproject.toml`.
- CI installs with `uv sync --locked`. The build fails if `uv.lock` does not match `pyproject.toml`.
- `requires-python`, the allowed Python version in `pyproject.toml`, matches production.
- pip-audit runs in CI. It fails the build on a dependency with a known vulnerability.

**import-linter** — the dependency rule as a build failure:

```toml
# pyproject.toml
[tool.importlinter]
root_package = "app"

[[tool.importlinter.contracts]]
name = "Layers point inward"
type = "layers"
layers = ["app.main", "app.composition", "app.api", "app.adapters", "app.application", "app.domain"]

[[tool.importlinter.contracts]]
name = "Domain is framework-free"
type = "forbidden"
source_modules = ["app.domain"]
forbidden_modules = ["fastapi", "sqlalchemy", "pydantic", "starlette", "httpx"]

[[tool.importlinter.contracts]]
name = "Application is infrastructure-free"
type = "forbidden"
source_modules = ["app.application"]
forbidden_modules = ["fastapi", "sqlalchemy", "httpx", "app.adapters"]

[[tool.importlinter.contracts]]
name = "Settings enter only at the composition root"
type = "forbidden"
source_modules = ["app.domain", "app.application", "app.adapters", "app.api"]
forbidden_modules = ["app.settings"]

[[tool.importlinter.contracts]]
name = "API never touches adapters"
type = "forbidden"
source_modules = ["app.api"]
forbidden_modules = ["app.adapters"]
```

Run with `lint-imports`. The `layers` list goes from high to low. A higher layer may import a lower
one, never the reverse. So `layers` alone would let `app.api` import `app.adapters`, and the last
contract forbids it. Forbidden contracts also catch indirect imports. That is why `AppContainer`
lives in `app.api`: an `app.api` module that imported `app.composition` would reach every adapter
through it.

**ruff** — `ASYNC` is the highest-value rule family here:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "ASYNC", "S", "T20", "SIM", "TID", "RUF"]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"

[tool.ruff.lint.mccabe]
max-complexity = 8
```

**mypy strict** — without it, `Protocol` ports are decorative: nothing verifies an adapter actually
satisfies the port it is injected as.

```toml
[tool.mypy]
strict = true
plugins = ["pydantic.mypy"]
warn_unreachable = true
```

Wire all three into pre-commit and CI. `lint-imports` failing on a wrong-direction import is the
whole point — it is the rule enforcing itself.

## 14. Deploys and shutdown

- A deploy stops a process with SIGTERM, the stop signal. On SIGTERM, `/ready` turns false first. The process keeps serving a few seconds while the load balancer notices. Then it finishes in-flight requests, and `lifespan` closes clients.
- Set a graceful shutdown timeout. A stuck request must not block the deploy forever.
- Keep-alive timeout is how long an idle connection stays open. The app's must be longer than the load balancer's. Uvicorn's default is 5 seconds, and many load balancers use 60. Otherwise clients get random 502 errors.
- Old and new versions run at the same time during a deploy. Every message format and API change works with both.

The uvicorn flags for §10 and §14. The numbers are examples. Take workers from the CPU limit and
keep-alive from the load balancer:

```bash
uvicorn app.main:app --workers 4 --limit-concurrency 200 \
  --timeout-keep-alive 75 --timeout-graceful-shutdown 30
```

## 15. Audit mode

When reviewing an existing backend, run these signals, then report as
`issue / location / root cause / fix`, ordered by blast radius. Do not fix while auditing unless
asked — a violation list is more useful than a surprise refactor.

```bash
# §2 — old APIs the model remembers
rg -n '@app\.on_event|\.utcnow\(|class Config:|@validator\b|\.dict\(\)|parse_obj\(|orm_mode|session\.query\(|declarative_base\(|get_event_loop\(|= Depends\(' src/
rg -n '^from typing import .*\b(Optional|List|Dict|Union)\b|^import (requests|aioredis)|^from (jose|passlib)\b|^from pydantic import .*\bBaseSettings\b' src/

# §3.2 rule 3 — infrastructure built at import time (module-level, column 0)
rg -n '^[a-z_]+ *= *(create_async_engine|create_engine|.*Client|.*Session)\(' src/

# §3.2 rule 4 — config read outside the composition root
rg -n 'from .*(config|settings) import|import settings' src/app/{domain,application,adapters,api}

# §3.2 rule 6 — frameworks in the domain
rg -n '^(from|import) (fastapi|sqlalchemy|pydantic|starlette|httpx)' src/app/domain/

# §3.2 rule 2 — service inheriting its adapter
rg -n 'class \w*(Service|UseCase)\(\w*(Repository|Client|Adapter|Store)\)'

# §3.2 rule 1 — logic inside dependencies (await/if/for in a Depends provider)
rg -n -A15 '^(async )?def get_\w+\(' src/app/api/dependencies.py | rg -n '(await|if |for |\.search\(|\.upsert\()'

# §3.2 rule 7 — grab-bag modules
fd -g '{utils,helpers,common,misc}.py' src/

# §3.2 rule 8 — routes reaching into app.state, or handlers in main.py
rg -n 'app\.state\.' src/app/api/ -g '!dependencies.py'
rg -n '@app\.(get|post|put|patch|delete|websocket)' src/app/main.py

# §3.2 rule 5 — DTOs in the wrong layer
rg -ln 'BaseModel' src/app/{adapters,infrastructure} 2>/dev/null

# §3.2 rule 9 — layer names as peers inside one folder (vertical slice with erased boundaries)
fd -t d -x sh -c 'ls "$1" | rg -q "repository|extractor|transformer" && ls "$1" | rg -q "service" && echo "$1"' _ {} \; src/

# §4 — blocking calls, sync dependencies, BaseHTTPMiddleware
rg -n 'requests\.|time\.sleep|\.read\(\)|boto3|socket\.getaddrinfo|\bOpenAI\(|redis\.Redis\(' src/ -g '*.py'
rg -n '^def ' src/app/api/dependencies.py src/app/api/auth.py
rg -n 'BaseHTTPMiddleware' src/

# §5 — mutable module-level state, process-local locks
rg -n '^[a-z_]+(: [^=]+)? = (\{\}|\[\]|set\(\)|dict\(\)|list\(\)|0)$' src/
rg -n 'asyncio\.Lock\(' src/

# §6 — f-string SQL, OFFSET pagination, total counts, random IDs, blocking index builds
rg -n "(text|execute)\(f[\"']" src/
rg -n '\.offset\(|OFFSET|func\.count\(' src/
rg -n 'uuid4\(' src/
rg -n 'create_index\(' -g '**/versions/*.py' | rg -v 'postgresql_concurrently=True'

# §9 — unsafe loads, secrets compared with ==, wildcard CORS
rg -n 'pickle\.loads|yaml\.load\(' src/
rg -n '(secret|token|api_key|password)\w* *[!=]= ' src/
rg -n 'allow_origins=\["\*"\]' src/

# §10 — in-process caches with no TTL
rg -n '@(functools\.)?(lru_cache|cache)\b' src/
```

Also check by reading: are there tests that exercise a business rule without touching infrastructure?
If not, §3.2 rules 2 and 6 are violated regardless of what the greps say.

## 16. Calibration

Full ceremony is for code carrying business consequence. A three-endpoint internal tool does not
need bounded contexts, and a CRUD passthrough does not need a use case class (§3.3).

What never relaxes at any project size: **no import-time infrastructure, settings injected from one
place, no business logic in route handlers or `Depends`.** Those three cost nothing on day one and
are expensive to retrofit on day two hundred. §1 and §2 never relax either.

§10 applies when a load test says it does. Add replicas, shards or a CDN when a measured number
needs them, not before.
