from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import engine, Base
from app.routers import auth, faculty, admin

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tablolar yoksa oluştur
    Base.metadata.create_all(bind=engine)
    # İlk admin kullanıcısını oluştur (yoksa)
    _seed_admin()
    yield


def _seed_admin():
    from app.database import SessionLocal
    from app.models.models import User, UserRole
    from app.services.auth import hash_password
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.role == UserRole.admin).first():
            admin_user = User(
                username="admin",
                email="bap@universite.edu.tr",
                full_name="BAP Koordinatörü",
                hashed_password=hash_password("Admin2024!"),
                role=UserRole.admin,
            )
            db.add(admin_user)
            db.commit()
            print("✓ Varsayılan admin oluşturuldu: admin / Admin2024!")
            print("  !! Üretim ortamında şifreyi değiştirin !!")
    finally:
        db.close()


app = FastAPI(
    title=settings.app_title,
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(faculty.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return RedirectResponse("/giris")


@app.exception_handler(302)
async def redirect_handler(request: Request, exc):
    return RedirectResponse(url=exc.headers["Location"])
