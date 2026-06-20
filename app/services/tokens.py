import secrets
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.models import LoginToken, User


TOKEN_HOURS = 48  # Link 48 saat geçerli


def create_login_token(user: User, db: Session) -> str:
    """
    Kullanıcı için tek kullanımlık token üretir, DB'ye yazar.
    Aynı kullanıcının eski geçerli tokenlerini iptal eder.
    Tokeni (ham string) döndürür.
    """
    # Eski kullanılmamış tokenleri temizle
    db.query(LoginToken).filter(
        LoginToken.user_id == user.id,
        LoginToken.used_at == None,
    ).delete()

    raw = secrets.token_urlsafe(32)  # 256-bit güvenli rastgele
    token = LoginToken(
        user_id=user.id,
        token=raw,
        expires_at=datetime.utcnow() + timedelta(hours=TOKEN_HOURS),
    )
    db.add(token)
    db.commit()
    return raw


def consume_token(raw: str, db: Session) -> User | None:
    """
    Tokeni doğrular; geçerliyse işaretler ve User'ı döndürür.
    Geçersiz, süresi dolmuş veya kullanılmış ise None döner.
    """
    record = db.query(LoginToken).filter(LoginToken.token == raw).first()
    if not record:
        return None
    if record.used_at is not None:
        return None  # Zaten kullanılmış
    if datetime.utcnow() > record.expires_at:
        return None  # Süresi dolmuş
    record.used_at = datetime.utcnow()
    db.commit()
    return record.user
