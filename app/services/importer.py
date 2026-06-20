"""
Proje listesini CSV veya Excel'den içe aktarır.

Desteklenen sütunlar:
    proje_kodu / project_code / Proje Kodu
    baslik / title / Proje Başlığı
    butce / budget / Bütçe
    yurutucu / Proje Yürütücüsü / pi_name
    kullanici_adi / username / Kullanıcı Adı
    mail / email / E-Posta / eposta
    fakulte / faculty / Fakülte
    bolum / department / Bölüm
    baslangic / start_date / Başlangıç Tarihi
    bitis / end_date / Bitiş Tarihi
    tur / type / Proje Türü
"""
import io
from typing import Optional
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import Session

from app.models.models import Project, User, UserRole
from app.services.auth import hash_password


COLUMN_MAP = {
    # Proje kodu
    "proje_kodu": "project_code", "project_code": "project_code",
    "proje kodu": "project_code", "kod": "project_code",
    # Başlık
    "baslik": "title", "başlık": "title", "title": "title",
    "proje başlığı": "title", "proje basligi": "title",
    "proje adi": "title", "proje adı": "title", "proje başligi": "title",
    # Bütçe — parantezli varyantlar dahil
    "butce": "budget", "bütçe": "budget", "budget": "budget",
    "bütçe (tl)": "budget", "butce (tl)": "budget",
    "bütçe(tl)": "budget", "bütçe tl": "budget",
    # Yürütücü adı
    "yurutucu": "pi_name", "yürütücü": "pi_name", "pi": "pi_name",
    "proje yürütücüsü": "pi_name", "proje yurutucu": "pi_name",
    "ad soyad": "pi_name", "ad_soyad": "pi_name", "adsoyad": "pi_name",
    "isim": "pi_name", "tam ad": "pi_name",
    # Kullanıcı adı
    "kullanici_adi": "username", "kullanıcı adı": "username",
    "kullanici adi": "username", "username": "username",
    # E-posta
    "mail": "email", "e-posta": "email", "eposta": "email",
    "email": "email", "e_posta": "email",
    "yurutucu_email": "email", "pi_email": "email", "e posta": "email",
    # Fakülte
    "fakulte": "faculty", "fakülte": "faculty", "faculty": "faculty",
    # Bölüm — slash'lı varyant (Bölüm/Birim)
    "bolum": "department", "bölüm": "department", "department": "department",
    "bölüm/birim": "department", "bolum/birim": "department",
    "birim": "department", "bölüm birim": "department",
    # Tarihler
    "baslangic": "start_date", "başlangıç": "start_date",
    "start_date": "start_date", "başlangıç tarihi": "start_date",
    "kabul tarihi": "start_date", "kabul_tarihi": "start_date",
    "bitis": "end_date", "bitiş": "end_date",
    "end_date": "end_date", "bitiş tarihi": "end_date",
    # Başvuru yılı (proje type/year — bilgi amaçlı saklanır)
    "başvuru yılı": "application_year", "basvuru yili": "application_year",
    "başvuru_yılı": "application_year", "yıl": "application_year",
    # Proje türü
    "tur": "project_type", "tür": "project_type",
    "type": "project_type", "proje türü": "project_type",
}


def _clean_col(name: str) -> str:
    """Sütun adını normalleştirir: küçük harf, boşluk/parantez/noktalama temizler."""
    import re
    s = str(name).strip().lower()
    # Parantez içini koru ama parantezleri kaldır: "Bütçe (TL)" → "bütçe tl"
    s = re.sub(r"[()_]", " ", s)
    # Fazla boşlukları tek boşluğa indir
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = [_clean_col(c) for c in df.columns]
    df.columns = cleaned
    rename = {col: COLUMN_MAP[col] for col in df.columns if col in COLUMN_MAP}
    return df.rename(columns=rename)


def _str(val) -> str:
    return str(val).strip() if pd.notna(val) else ""


_TITLE_PREFIXES = (
    "prof. dr.", "doç. dr.", "dr. öğr. üyesi", "dr.öğr.üyesi",
    "öğr. gör. dr.", "öğr. gör.", "arş. gör. dr.", "arş. gör.",
    "dr.", "prof.", "doç.", "uzm.",
)

def _parse_date(val) -> Optional[datetime]:
    """Excel/CSV'den tarih ayrıştırır (Timestamp, datetime veya string)."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, datetime):
        return val
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime()
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
                "%Y.%m.%d", "%d.%m.%y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _strip_title(name: str) -> str:
    """Akademik unvanı ismin başından çıkarır."""
    low = name.lower()
    for prefix in _TITLE_PREFIXES:
        if low.startswith(prefix):
            name = name[len(prefix):].strip()
            low = name.lower()
    return name.strip()


def import_projects_from_file(
    file_content: bytes,
    filename: str,
    db: Session,
    default_password: str = "Bap2024!",
) -> dict:
    """
    Dosyayı okur, projeleri ve yürütücüleri DB'ye yazar.
    Var olan proje_kodu'nu günceller (upsert).
    Döner: {imported: int, updated: int, errors: list[str]}
    """
    if filename.lower().endswith(".csv"):
        try:
            df = pd.read_csv(io.BytesIO(file_content), encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(file_content), encoding="latin-1")
    else:
        df = pd.read_excel(io.BytesIO(file_content))

    df = _normalize_columns(df)

    if "project_code" not in df.columns:
        raise ValueError(
            "Dosyada 'Proje Kodu' sütunu bulunamadı. "
            "Lütfen sütun başlığını kontrol edin."
        )

    imported, updated, errors = 0, 0, []

    for idx, row in df.iterrows():
        try:
            code = _str(row.get("project_code"))
            if not code:
                continue

            # — Yürütücü bilgilerini topla —
            pi_name     = _strip_title(_str(row.get("pi_name")))
            username    = _str(row.get("username"))
            email       = _str(row.get("email"))
            faculty     = _str(row.get("faculty"))
            department  = _str(row.get("department"))

            pi_user = None
            if pi_name or email or username:
                # Kullanıcı adını belirle: sütundan al, yoksa emailden üret
                if not username:
                    if email:
                        username = email.split("@")[0]
                    elif pi_name:
                        username = pi_name.lower().replace(" ", ".")

                # Ad yoksa kullanıcı adından üret
                if not pi_name:
                    pi_name = username

                pi_user = db.query(User).filter(User.username == username).first()
                if not pi_user:
                    pi_user = User(
                        username=username,
                        email=email or None,
                        full_name=pi_name,
                        role=UserRole.faculty,
                        faculty=faculty or None,
                        department=department or None,
                        hashed_password=hash_password(default_password),
                    )
                    db.add(pi_user)
                    db.flush()
                else:
                    # Mevcut kullanıcıyı güncelle (email/fakülte/bölüm değiştiyse)
                    if email and email != (pi_user.email or ""):
                        pi_user.email = email
                    if faculty:
                        pi_user.faculty = faculty
                    if department:
                        pi_user.department = department

            # — Bütçe —
            budget = None
            raw_budget = row.get("budget")
            if pd.notna(raw_budget) and str(raw_budget).strip():
                try:
                    budget = float(
                        str(raw_budget)
                        .replace(",", ".")
                        .replace("₺", "")
                        .replace("TL", "")
                        .replace(" ", "")
                    )
                except ValueError:
                    pass

            # — Tarihler ve tür —
            start_date = _parse_date(row.get("start_date"))
            end_date   = _parse_date(row.get("end_date"))
            project_type = _str(row.get("project_type")) or None

            application_year: Optional[int] = None
            raw_year = row.get("application_year")
            if raw_year is not None and pd.notna(raw_year) and str(raw_year).strip():
                try:
                    application_year = int(float(str(raw_year).strip()))
                except (ValueError, TypeError):
                    pass

            # — Proje upsert —
            project = db.query(Project).filter(Project.project_code == code).first()
            if project:
                project.title = _str(row.get("title")) or project.title
                if budget is not None:
                    project.budget = budget
                if pi_user:
                    project.principal_investigator = pi_user
                if department:
                    project.department = department
                if project_type:
                    project.project_type = project_type
                if start_date:
                    project.start_date = start_date
                if end_date:
                    project.end_date = end_date
                if application_year:
                    project.application_year = application_year
                updated += 1
            else:
                project = Project(
                    project_code=code,
                    title=_str(row.get("title")) or code,
                    budget=budget,
                    department=department or None,
                    project_type=project_type,
                    start_date=start_date,
                    end_date=end_date,
                    application_year=application_year,
                    principal_investigator=pi_user,
                )
                db.add(project)
                imported += 1

        except Exception as e:
            errors.append(f"Satır {int(idx) + 2}: {e}")

    db.commit()
    return {"imported": imported, "updated": updated, "errors": errors}
