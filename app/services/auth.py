from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.models import User, UserRole

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


def authenticate_ldap(username: str, password: str) -> Optional[dict]:
    """
    LDAP ile kimlik doğrulama.
    BT'den bilgiler alındıktan sonra .env'de LDAP_ENABLED=true yapılır.
    Döndürülen dict: {username, email, full_name, department}
    """
    try:
        from ldap3 import Server, Connection, ALL, NTLM
        server = Server(settings.ldap_host, port=settings.ldap_port, get_info=ALL)
        # Önce servis hesabıyla bağlan, kullanıcıyı bul
        bind_conn = Connection(
            server,
            user=settings.ldap_bind_dn,
            password=settings.ldap_bind_password,
            auto_bind=True,
        )
        bind_conn.search(
            settings.ldap_base_dn,
            f"(sAMAccountName={username})",
            attributes=["mail", "displayName", "department", "distinguishedName"],
        )
        if not bind_conn.entries:
            return None
        entry = bind_conn.entries[0]
        user_dn = str(entry.distinguishedName)

        # Kullanıcının kendi şifresiyle doğrula
        user_conn = Connection(server, user=user_dn, password=password)
        if not user_conn.bind():
            return None

        return {
            "username": username,
            "email": str(entry.mail) if entry.mail else f"{username}@universite.edu.tr",
            "full_name": str(entry.displayName) if entry.displayName else username,
            "department": str(entry.department) if entry.department else None,
        }
    except Exception as e:
        print(f"LDAP hatası: {e}")
        return None


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """
    Kimlik doğrulama mantığı (öncelik sırası):

    1. LDAP etkinse önce LDAP'ı dene.
       - Başarılıysa: kullanıcıyı DB'de yoksa oluştur, döndür.
       - Başarısızsa (kurumdan ayrılmış, hesap kilitli vb.):
         yerel DB'ye düş — yerel şifre varsa kabul et.

    2. LDAP kapalıysa (geliştirme ortamı veya LDAP bilgisi henüz yok):
       doğrudan yerel DB şifresiyle doğrula.

    Bu sayede kurumdan ayrılan hocalar için admin elle
    yerel şifre atayabilir; o hoca LDAP olmadan giriş yapar.
    """
    if settings.ldap_enabled:
        ldap_info = authenticate_ldap(username, password)
        if ldap_info:
            # LDAP başarılı — DB'de yoksa oluştur
            user = db.query(User).filter(User.username == username).first()
            if not user:
                user = User(
                    username=ldap_info["username"],
                    email=ldap_info["email"],
                    full_name=ldap_info["full_name"],
                    department=ldap_info["department"],
                    role=UserRole.faculty,
                    hashed_password=None,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            return user
        # LDAP başarısız — yerel hesaba bak (kurumdan ayrılanlar için)
        print(f"LDAP başarısız ({username}), yerel hesap deneniyor...")

    # Yerel DB kontrolü (LDAP kapalıysa veya LDAP başarısız olduysa)
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
