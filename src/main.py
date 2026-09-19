# Каркас FastAPI з ендпоінтами перевірки працездатності:
# Імпортуємо декоратор для створення асинхронного контекстного менеджера (життєвий цикл застосунку)
from contextlib import asynccontextmanager

# Імпортуємо головний клас вебфреймворка FastAPI
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Імпортуємо з нашого модуля БД спільний базовий клас моделей (Base) та рушій підключень (engine)
from src.database import Base, engine, get_db
from src.models import Petition, User, UserRole, Vote
from src.schemas import (
    PetitionCreate,
    PetitionResponse,
    PetitionUpdate,
    Token,
    UserCreate,
    UserResponse,
    VoteCreate,
)
from src.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)


# Декоратор перетворює асинхронну функцію-генератор на контекстний менеджер для FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код ДО ключового слова yield виконується один раз під час запуску (startup) сервера:
    # engine.begin() відкриває транзакційне асинхронне з'єднання (Connection)
    async with engine.begin() as conn:
        # Base.metadata.create_all — синхронний метод SQLAlchemy, тому run_sync запускає його
        # в окремому потоці, створюючи всі відсутні таблиці в БД згідно з наявними моделями
        await conn.run_sync(Base.metadata.create_all)

    # yield передає керування запущеному застосунку й тримає його активним для обробки запитів.
    # Код ПІСЛЯ yield (якщо його додати) виконається один раз при вимкненні (shutdown) сервера
    yield


# Створюємо головний екземпляр застосунку FastAPI з метаданими для документації Swagger/ReDoc
app = FastAPI(
    title="Local Petitions Service API",  # Назва сервісу в документації (/docs)
    description="Electronic petitions API with RBAC and JWT Authentication",  # Опис призначення API
    version="2.0.0",  # Поточна версія API
    lifespan=lifespan,  # Підключаємо наш контекстний менеджер життєвого циклу
)


# 1. АВТЕНТИФІКАЦІЯ ТА РЕЄСТРАЦІЯ
@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Захист: реєстрація дозволена лише як звичайний користувач (якщо не передано явно)
    role_to_set = UserRole.ADMIN.value if user_data.role == "admin" else UserRole.USER.value
    new_user = User(
        username=user_data.username,
        hashed_password=hash_password(user_data.password),
        role=role_to_set,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=Token)
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
    return {"access_token": token, "token_type": "bearer"}


# 2. ДОМАШНІ СТОРІНКИ-ЗАГЛУШКИ
@app.get("/users/me")
async def user_dashboard(current_user: User = Depends(get_current_user)):
    return {
        "message": f"Welcome to User Dashboard, {current_user.username}!",
        "role": current_user.role,
        "status": "active",
    }


@app.get("/admin/dashboard")
async def admin_dashboard(admin: User = Depends(require_admin)):
    return {
        "message": "Welcome to Admin Control Panel",
        "admin_user": admin.username,
        "access": "Full System Management",
    }


# 3. БІЗНЕС-ЛОГІКА ПЕТИЦІЙ (MVP)
@app.post(
    "/petitions/",
    response_model=PetitionResponse,
    status_code=status.HTTP_201_CREATED,
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
        author_id=current_user.id,
    )
    db.add(new_petition)
    await db.commit()
    await db.refresh(new_petition)
    return new_petition


# Оновлення петиції з захистом від IDOR (горизонтальне розмежування прав)
@app.put("/petitions/{petition_id}", response_model=PetitionResponse)
async def update_petition(
    petition_id: int,
    update_data: PetitionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Petition).where(Petition.id == petition_id))
    petition = result.scalars().first()
    if not petition:
        raise HTTPException(status_code=404, detail="Petition not found")

    # IDOR Check: Тільки автор може редагувати петицію
    if petition.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot modify someone else's petition",
        )

    if update_data.title:
        petition.title = update_data.title
    if update_data.description:
        petition.description = update_data.description

    await db.commit()
    await db.refresh(petition)
    return petition


@app.post("/petitions/{petition_id}/vote", status_code=status.HTTP_201_CREATED)
async def vote_for_petition(
    petition_id: int,
    vote_data: VoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Petition).where(Petition.id == petition_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Petition not found")

    # Перевірка на дублікат голосу
    existing_vote = await db.execute(
        select(Vote).where(
            Vote.petition_id == petition_id,
            Vote.voter_signature_hash == vote_data.voter_signature_hash,
        )
    )
    if existing_vote.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate vote: Signature already used for this petition",
        )

    vote = Vote(
        petition_id=petition_id,
        voter_signature_hash=vote_data.voter_signature_hash,
    )
    db.add(vote)
    await db.commit()
    return {"status": "success", "message": "Vote recorded successfully"}


# Декоратор реєструє обробник для GET-запиту на шлях /health;
# tags=["System"] групує цей ендпоінт в окрему секцію "System" в інтерфейсі Swagger
@app.get("/health", tags=["System"])
async def health_check():
    # Повертає простий JSON для моніторингу працездатності (використовується оркестраторами, наприклад, Docker/K8s)
    return {"status": "ok", "service": "petitions-service"}


# Декоратор реєструє обробник для кореневого URL (GET /)
@app.get("/", tags=["Root"])
async def root():
    # Повертає вітальне JSON-повідомлення, підтверджуючи, що сервіс успішно піднявся
    return {"message": "Сервіс місцевих електронних петицій працює"}
