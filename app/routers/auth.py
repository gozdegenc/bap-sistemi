from fastapi import APIRouter, Depends, HTTPException, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth import authenticate_user, create_access_token, decode_token
from app.models.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/giris"})
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = require_user(request, db)
    if user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Bu sayfaya erişim yetkiniz yok.")
    return user


@router.get("/giris", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("shared/login.html", {"request": request})


@router.post("/giris")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username, password)
    if not user or not user.is_active:
        return templates.TemplateResponse(
            "shared/login.html",
            {"request": request, "error": "Kullanıcı adı veya şifre hatalı."},
            status_code=401,
        )
    token = create_access_token({"sub": user.username, "role": user.role.value})
    response = RedirectResponse(
        url="/yonetim" if user.role.value == "admin" else "/portal",
        status_code=302,
    )
    response.set_cookie(
        "access_token", token,
        httponly=True, samesite="lax", max_age=60 * 60 * 8,
    )
    return response


@router.get("/cikis")
async def logout():
    response = RedirectResponse(url="/giris", status_code=302)
    response.delete_cookie("access_token")
    return response


# ── Tek kullanımlık link ile giriş ──────────────────────────────────────────

from app.services.tokens import consume_token
from app.services.auth import hash_password
from typing import Optional


@router.get("/giris/link/{token}", response_class=HTMLResponse)
async def magic_link_landing(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Hoca linke tıkladığında buraya gelir.
    Token geçerliyse şifre belirleme formunu gösterir.
    """
    record = db.query(__import__('app.models.models', fromlist=['LoginToken']).LoginToken).filter_by(token=token).first()
    # Sadece varlık ve süre kontrolü — henüz tüketme
    from datetime import datetime
    if not record or record.used_at or datetime.utcnow() > record.expires_at:
        return templates.TemplateResponse(
            "shared/link_gecersiz.html", {"request": request}
        )
    return templates.TemplateResponse(
        "shared/sifre_belirle.html",
        {"request": request, "token": token, "full_name": record.user.full_name},
    )


@router.post("/giris/link/{token}")
async def magic_link_set_password(
    token: str,
    request: Request,
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    """Şifre belirleme formunu işler, tokeni tüketir, oturumu açar."""
    if password != password2:
        from app.models.models import LoginToken
        record = db.query(LoginToken).filter_by(token=token).first()
        name = record.user.full_name if record else ""
        return templates.TemplateResponse(
            "shared/sifre_belirle.html",
            {"request": request, "token": token, "full_name": name,
             "error": "Şifreler eşleşmiyor."},
        )
    if len(password) < 8:
        from app.models.models import LoginToken
        record = db.query(LoginToken).filter_by(token=token).first()
        name = record.user.full_name if record else ""
        return templates.TemplateResponse(
            "shared/sifre_belirle.html",
            {"request": request, "token": token, "full_name": name,
             "error": "Şifre en az 8 karakter olmalı."},
        )

    user = consume_token(token, db)
    if not user:
        return templates.TemplateResponse(
            "shared/link_gecersiz.html", {"request": request}
        )

    # Şifreyi kaydet
    user.hashed_password = hash_password(password)
    db.commit()

    # Oturumu aç
    jwt_token = create_access_token({"sub": user.username, "role": user.role.value})
    response = RedirectResponse(
        url="/yonetim" if user.role.value == "admin" else "/portal",
        status_code=302,
    )
    response.set_cookie(
        "access_token", jwt_token,
        httponly=True, samesite="lax", max_age=60 * 60 * 8,
    )
    return response
