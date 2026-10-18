# Каркас FastAPI з ендпоінтами сервісу петицій та контролем доступу (RBAC, Lab 2 & 3)
import hashlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.database import get_db
from src.init_db import init_models, seed_data
from src.models import Petition, PetitionStatus, User, UserRole, Vote
from src.schemas import (
    AdminStats,
    PetitionCreate,
    PetitionResponse,
    PetitionStatusUpdate,
    PetitionUpdate,
    Token,
    UserCreate,
    UserResponse,
    UserUpdate,
    VoteCreate,
)
from src.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "src" / "static"
logger = logging.getLogger("petitions_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Виконується під час запуску (startup) сервера:
    await init_models()
    await seed_data()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Electronic petitions API with Environment Separation, RBAC, and IDOR protection",
    version="3.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)


# Middleware безпечної обробки непередбачених помилок 500 (Lab 3: приховування внутрішніх стектрейсів у Production)
@app.middleware("http")
async def security_exception_middleware(request: Request, call_next):
    # На рівні HTTP-middleware перехоплюються всі непередбачені винятки (try ... except Exception as exc):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.error(f"Internal unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
        if settings.DEBUG:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "Internal Server Error",
                    "debug_error": str(exc),
                    "environment": settings.APP_ENV,
                },
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Внутрішня помилка сервера. Будь ласка, зверніться до служби підтримки.",
            },
        )


# Монтування статичних файлів для веб-інтерфейсу
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# 0. ГОЛОВНА СТОРІНКА / WEB UI
@app.get("/", tags=["UI"])
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            str(index_file),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {"message": "Сервіс місцевих електронних петицій працює"}


# 1. АВТЕНТИФІКАЦІЯ ТА РЕЄСТРАЦІЯ
@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Роль: звичайний користувач за замовчуванням; опціонально дозволено роль admin для навчальних тестів
    role_to_set = UserRole.ADMIN.value if user_data.role == UserRole.ADMIN.value else UserRole.USER.value
    new_user = User(
        username=user_data.username,
        hashed_password=hash_password(user_data.password),
        role=role_to_set,
        full_name=user_data.full_name,
        email=user_data.email,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=Token, tags=["Auth"])
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": user.username, "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
    }


# 2. ДОМАШНІ СТОРІНКИ-ЗАГЛУШКИ ТА ПРОФІЛІ
@app.get("/users/me", tags=["Users"])
async def user_dashboard(current_user: User = Depends(get_current_user)):
    return {
        "message": f"Welcome to User Dashboard, {current_user.username}!",
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "created_at": current_user.created_at,
        "status": "active",
    }


@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
async def get_user_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# Оновлення профілю користувача з захистом від IDOR
@app.put("/users/{user_id}", response_model=UserResponse, tags=["Users"])
async def update_user_profile(
    user_id: int,
    profile_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalars().first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # IDOR Check: звичайний користувач може змінювати лише ВЛАСНИЙ профіль
    if current_user.id != user_id and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot modify another user's profile",
        )

    if profile_data.full_name is not None:
        target_user.full_name = profile_data.full_name
    if profile_data.email is not None:
        target_user.email = profile_data.email

    await db.commit()
    await db.refresh(target_user)
    return target_user


# 3. АДМІН-ПАНЕЛЬ ТА КЕРУВАННЯ
@app.get("/admin/dashboard", tags=["Admin"])
async def admin_dashboard(admin: User = Depends(require_admin)):
    return {
        "message": "Welcome to Admin Control Panel",
        "admin_user": admin.username,
        "access": "Full System Management",
    }


@app.get("/admin/stats", response_model=AdminStats, tags=["Admin"])
async def admin_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_petitions = (await db.execute(select(func.count(Petition.id)))).scalar() or 0
    total_votes = (await db.execute(select(func.count(Vote.id)))).scalar() or 0

    statuses = [s.value for s in PetitionStatus]
    status_counts = {}
    for st in statuses:
        count = (await db.execute(select(func.count(Petition.id)).where(Petition.status == st))).scalar() or 0
        status_counts[st] = count

    return {
        "total_users": total_users,
        "total_petitions": total_petitions,
        "total_votes": total_votes,
        "petitions_by_status": status_counts,
    }


@app.get("/admin/users", response_model=List[UserResponse], tags=["Admin"])
async def admin_get_all_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.id.asc()))
    return result.scalars().all()


# 4. БІЗНЕС-ЛОГІКА ПЕТИЦІЙ (MVP)
@app.get("/petitions/", response_model=List[PetitionResponse], tags=["Petitions"])
async def list_petitions(
    q: Optional[str] = Query(None, description="Пошук за ключовими словами"),
    status_filter: Optional[str] = Query(None, alias="status", description="Фільтр за статусом"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Petition).options(selectinload(Petition.author), selectinload(Petition.votes))

    if q:
        query = query.where(Petition.title.ilike(f"%{q}%") | Petition.description.ilike(f"%{q}%"))
    if status_filter:
        query = query.where(Petition.status == status_filter)

    query = query.order_by(Petition.created_at.desc())
    result = await db.execute(query)
    petitions = result.scalars().all()

    response = []
    for p in petitions:
        response.append(
            PetitionResponse(
                id=p.id,
                title=p.title,
                description=p.description,
                target_votes=p.target_votes,
                status=p.status,
                author_id=p.author_id,
                author_username=p.author.username if p.author else None,
                votes_count=len(p.votes) if p.votes else 0,
                created_at=p.created_at,
            )
        )
    return response


@app.get("/petitions/{petition_id}", response_model=PetitionResponse, tags=["Petitions"])
async def get_petition_detail(
    petition_id: int,
    db: AsyncSession = Depends(get_db),
):
    query = select(Petition).options(selectinload(Petition.author), selectinload(Petition.votes)).where(Petition.id == petition_id)
    result = await db.execute(query)
    petition = result.scalars().first()
    if not petition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Petition not found")

    return PetitionResponse(
        id=petition.id,
        title=petition.title,
        description=petition.description,
        target_votes=petition.target_votes,
        status=petition.status,
        author_id=petition.author_id,
        author_username=petition.author.username if petition.author else None,
        votes_count=len(petition.votes) if petition.votes else 0,
        created_at=petition.created_at,
    )


@app.post(
    "/petitions/",
    response_model=PetitionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Petitions"],
)
async def create_petition(
    petition_data: PetitionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_petition = Petition(
        title=petition_data.title,
        description=petition_data.description,
        target_votes=petition_data.target_votes,
        status=PetitionStatus.ACTIVE.value,
        author_id=current_user.id,
    )
    db.add(new_petition)
    await db.commit()
    await db.refresh(new_petition)

    return PetitionResponse(
        id=new_petition.id,
        title=new_petition.title,
        description=new_petition.description,
        target_votes=new_petition.target_votes,
        status=new_petition.status,
        author_id=new_petition.author_id,
        author_username=current_user.username,
        votes_count=0,
        created_at=new_petition.created_at,
    )


# Оновлення петиції з захистом від IDOR (горизонтальне розмежування прав)
@app.put(
    "/petitions/{petition_id}",
    response_model=PetitionResponse,
    tags=["Petitions"],
)
async def update_petition(
    petition_id: int,
    update_data: PetitionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Petition).options(selectinload(Petition.author), selectinload(Petition.votes)).where(Petition.id == petition_id)
    result = await db.execute(query)
    petition = result.scalars().first()
    if not petition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Petition not found")

    # IDOR Check: Тільки автор може редагувати петицію
    if petition.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot modify someone else's petition",
        )

    if update_data.title is not None:
        petition.title = update_data.title
    if update_data.description is not None:
        petition.description = update_data.description

    await db.commit()
    await db.refresh(petition)

    return PetitionResponse(
        id=petition.id,
        title=petition.title,
        description=petition.description,
        target_votes=petition.target_votes,
        status=petition.status,
        author_id=petition.author_id,
        author_username=petition.author.username if petition.author else None,
        votes_count=len(petition.votes) if petition.votes else 0,
        created_at=petition.created_at,
    )


# Зміна статусу петиції адміністратором (вертикальне розмежування ролей)
@app.patch(
    "/petitions/{petition_id}/status",
    response_model=PetitionResponse,
    tags=["Petitions"],
)
async def update_petition_status(
    petition_id: int,
    status_data: PetitionStatusUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Petition).options(selectinload(Petition.author), selectinload(Petition.votes)).where(Petition.id == petition_id)
    result = await db.execute(query)
    petition = result.scalars().first()
    if not petition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Petition not found")

    valid_statuses = [s.value for s in PetitionStatus]
    if status_data.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    petition.status = status_data.status
    await db.commit()
    await db.refresh(petition)

    return PetitionResponse(
        id=petition.id,
        title=petition.title,
        description=petition.description,
        target_votes=petition.target_votes,
        status=petition.status,
        author_id=petition.author_id,
        author_username=petition.author.username if petition.author else None,
        votes_count=len(petition.votes) if petition.votes else 0,
        created_at=petition.created_at,
    )


# Видалення петиції (доступно автору або адміністратору)
@app.delete("/petitions/{petition_id}", tags=["Petitions"])
async def delete_petition(
    petition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Petition).where(Petition.id == petition_id))
    petition = result.scalars().first()
    if not petition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Petition not found")

    if petition.author_id != current_user.id and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only author or admin can delete this petition",
        )

    await db.delete(petition)
    await db.commit()
    return {"status": "success", "message": f"Petition {petition_id} deleted successfully"}


# Голосування за петицію
@app.post(
    "/petitions/{petition_id}/vote",
    status_code=status.HTTP_201_CREATED,
    tags=["Petitions"],
)
async def vote_for_petition(
    petition_id: int,
    vote_data: VoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Petition).where(Petition.id == petition_id))
    petition = result.scalars().first()
    if not petition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Petition not found")

    if petition.status not in [PetitionStatus.ACTIVE.value, PetitionStatus.UNDER_REVIEW.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voting closed: petition is not active",
        )

    # Якщо хеш підпису не передано явно, генеруємо унікальний підпис на основі user_id
    sig_hash = (
        vote_data.voter_signature_hash
        if vote_data.voter_signature_hash
        else hashlib.sha256(f"user_{current_user.id}_signed_petition_{petition_id}".encode()).hexdigest()
    )

    # Перевірка на дублікат голосу (за хешем підпису або user_id)
    existing_vote = await db.execute(
        select(Vote).where(
            Vote.petition_id == petition_id,
            (Vote.voter_signature_hash == sig_hash) | (Vote.user_id == current_user.id),
        )
    )
    if existing_vote.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate vote: Signature already used for this petition",
        )

    vote = Vote(
        petition_id=petition_id,
        user_id=current_user.id,
        voter_signature_hash=sig_hash,
    )
    db.add(vote)
    await db.commit()
    return {"status": "success", "message": "Vote recorded successfully"}


# 5. СИСТЕМНІ ЕНДПОІНТИ (Lab 3: Перевірка середовища та обробки помилок)
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "service": "petitions-service",
        "environment": settings.APP_ENV,
        "debug": settings.DEBUG,
        "database": settings.DATABASE_URL.split("///")[-1],
    }


@app.get("/system/env-info", tags=["System"])
async def env_info():
    """Повертає інформацію про поточне середовище виконання (Sandbox vs Production)."""
    return {
        "app_env": settings.APP_ENV,
        "project_name": settings.PROJECT_NAME,
        "debug_mode": settings.DEBUG,
        "database_url": settings.DATABASE_URL,
        "db_echo": settings.DB_ECHO,
        "seed_demo_data": settings.SEED_DEMO_DATA,
        "token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    }


# діагностичний тестовий маршрут /system/trigger-error
@app.get("/system/trigger-error", tags=["System"])
async def trigger_simulated_error():
    """Ендпоінт для тестування приховування внутрішніх стектрейсів при 500 помилці (Lab 3)."""
    raise RuntimeError("Симульований збій бази даних: непередбачена критична помилка рушія!")
