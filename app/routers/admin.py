from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime
import os

from app.database import get_db
from app.models.models import Project, Output, Attachment, User, OutputStatus, UserRole
from app.routers.auth import require_admin
from app.services.importer import import_projects_from_file
from app.services.reports import generate_pdf_report, generate_excel_report
from app.services.auth import hash_password

router = APIRouter(prefix="/yonetim")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def admin_home(
    request: Request,
    year: Optional[int] = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # DB'deki gerçek başvuru yılları
    available_years: list[int] = [
        r[0] for r in
        db.query(Project.application_year)
        .filter(Project.application_year.isnot(None))
        .distinct()
        .order_by(Project.application_year)
        .all()
    ]

    # Yıl filtresine göre temel sorgular
    if year:
        proj_q = db.query(Project).filter(Project.application_year == year)
        out_q  = db.query(Output).join(Project).filter(Project.application_year == year)
    else:
        proj_q = db.query(Project)
        out_q  = db.query(Output)

    stats = {
        "total_projects": proj_q.count(),
        "total_outputs":  out_q.count(),
        "pending":  out_q.filter(Output.status == OutputStatus.gonderildi).count(),
        "approved": out_q.filter(Output.status == OutputStatus.onaylandi).count(),
        "by_type": (
            out_q.with_entities(Output.output_type, func.count(Output.id))
            .filter(Output.status == OutputStatus.onaylandi)
            .group_by(Output.output_type)
            .all()
        ),
        "faculty_count": db.query(User).filter(User.role == UserRole.faculty).count(),
    }

    pending_q = (
        out_q.filter(Output.status == OutputStatus.gonderildi)
        .order_by(Output.created_at.desc())
        .limit(10)
    )
    recent_outputs = pending_q.all()

    return templates.TemplateResponse("admin/home.html", {
        "request": request, "user": user,
        "stats": stats, "recent_outputs": recent_outputs,
        "available_years": available_years, "current_year": year,
    })


@router.get("/ciktilar", response_class=HTMLResponse)
async def all_outputs(
    request: Request,
    durum: Optional[str] = None,
    tur: Optional[str] = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(Output)
    if durum:
        q = q.filter(Output.status == OutputStatus(durum))
    if tur:
        from app.models.models import OutputType
        q = q.filter(Output.output_type == OutputType(tur))
    outputs = q.order_by(Output.created_at.desc()).all()
    from app.models.models import OutputType
    return templates.TemplateResponse("admin/outputs.html", {
        "request": request, "user": user, "outputs": outputs,
        "output_types": OutputType, "statuses": OutputStatus,
        "current_durum": durum, "current_tur": tur,
    })


@router.get("/cikti/{output_id}", response_class=HTMLResponse)
async def output_detail(
    output_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output:
        raise HTTPException(404)
    return templates.TemplateResponse("admin/output_detail.html", {
        "request": request, "user": user, "output": output,
    })


@router.get("/ek/{attachment_id}")
async def download_attachment(
    attachment_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att or not os.path.exists(att.file_path):
        raise HTTPException(404)
    return FileResponse(
        att.file_path,
        media_type=att.mime_type or "application/octet-stream",
        filename=att.original_filename,
    )


@router.post("/cikti/{output_id}/onayla")
async def approve_output(
    output_id: int,
    admin_note: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output:
        raise HTTPException(404)
    output.status = OutputStatus.onaylandi
    output.admin_note = admin_note
    db.commit()
    return RedirectResponse("/yonetim/ciktilar?durum=Gönderildi", status_code=302)


@router.post("/cikti/{output_id}/reddet")
async def revize_output(
    output_id: int,
    admin_note: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output:
        raise HTTPException(404)
    output.status = OutputStatus.revize_istendi
    output.admin_note = admin_note
    db.commit()
    return RedirectResponse("/yonetim/ciktilar?durum=Gönderildi", status_code=302)


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, user: User = Depends(require_admin)):
    return templates.TemplateResponse("admin/import.html", {"request": request, "user": user})


@router.post("/import")
async def import_projects(
    request: Request,
    file: UploadFile = File(...),
    default_password: str = Form("Bap2024!"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    content = await file.read()
    try:
        result = import_projects_from_file(content, file.filename or "", db, default_password)
    except ValueError as e:
        return templates.TemplateResponse(
            "admin/import.html",
            {"request": request, "user": user, "error": str(e)},
        )
    return templates.TemplateResponse(
        "admin/import.html",
        {"request": request, "user": user, "result": result},
    )


@router.get("/rapor")
async def download_report(
    format: str = "pdf",
    year: Optional[int] = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    y = year or datetime.now().year
    if format == "excel":
        data = generate_excel_report(db, y)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=bap_rapor_{y}.xlsx"},
        )
    else:
        data = generate_pdf_report(db, y)
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=bap_rapor_{y}.pdf"},
        )


@router.get("/kullanicilar", response_class=HTMLResponse)
async def users_list(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.full_name).all()
    return templates.TemplateResponse("admin/users.html", {
        "request": request, "user": user, "users": users,
    })


@router.post("/kullanici/{user_id}/link-uret")
async def generate_login_link(
    request: Request,
    user_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Tek kullanımlık giriş linki üretir, sayfada gösterir."""
    from app.services.tokens import create_login_token
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404)
    token = create_login_token(target, db)
    # Sunucu adresini request'ten al
    base_url = str(request.base_url).rstrip("/")
    link = f"{base_url}/giris/link/{token}"
    users = db.query(User).order_by(User.full_name).all()
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "user": user,
        "users": users,
        "generated_link": link,
        "generated_for": target.full_name,
    })


@router.post("/kullanici/{user_id}/sifre-ata")
async def set_local_password(
    user_id: int,
    new_password: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Kurumdan ayrılan veya LDAP hesabı olmayan hocaya yerel şifre ata."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404)
    target.hashed_password = hash_password(new_password)
    db.commit()
    return RedirectResponse("/yonetim/kullanicilar?pw_success=1", status_code=302)


@router.post("/kullanici/{user_id}/sil")
async def delete_user(
    user_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404)
    if target.id == user.id or target.role == UserRole.admin:
        return RedirectResponse("/yonetim/kullanicilar?err=admin_delete", status_code=302)
    if target.outputs:
        return RedirectResponse("/yonetim/kullanicilar?err=has_outputs", status_code=302)
    for proj in target.led_projects:
        proj.principal_investigator_id = None
    db.delete(target)
    db.commit()
    return RedirectResponse("/yonetim/kullanicilar?deleted=1", status_code=302)


@router.post("/kullanici-ekle")
async def create_user(
    username: str = Form(...),
    email: Optional[str] = Form(None),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form("faculty"),
    department: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(400, "Bu kullanıcı adı zaten var.")
    new_user = User(
        username=username, email=email or None, full_name=full_name,
        hashed_password=hash_password(password),
        role=UserRole(role), department=department,
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse("/yonetim/kullanicilar?success=1", status_code=302)
