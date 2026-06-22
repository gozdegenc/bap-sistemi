import os, uuid, shutil
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models.models import Project, Output, OutputType, OutputStatus, Attachment, User
from app.routers.auth import require_user
from app.config import get_settings

router = APIRouter(prefix="/portal")
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


@router.get("", response_class=HTMLResponse)
async def portal_home(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    # Yürütücü veya araştırmacı olduğu projeler
    led = user.led_projects
    researched = user.research_projects
    all_projects = list({p.id: p for p in led + researched}.values())
    return templates.TemplateResponse("faculty/home.html", {
        "request": request, "user": user, "projects": all_projects,
    })


@router.get("/proje/{project_id}", response_class=HTMLResponse)
async def project_detail(
    request: Request, project_id: int,
    user: User = Depends(require_user), db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404)
    _check_project_access(user, project)
    return templates.TemplateResponse("faculty/project.html", {
        "request": request, "user": user, "project": project,
        "output_types": OutputType,
    })


@router.post("/proje/{project_id}/cikti-ekle")
async def add_output(
    request: Request,
    project_id: int,
    output_type: str = Form(...),
    title: str = Form(...),
    authors: Optional[str] = Form(None),
    publication_date: Optional[str] = Form(None),
    identifier: Optional[str] = Form(None),
    publisher_venue: Optional[str] = Form(None),
    acknowledgement_note: Optional[str] = Form(None),
    relation_note: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404)
    _check_project_access(user, project)

    output = Output(
        project_id=project_id,
        submitted_by_id=user.id,
        output_type=OutputType(output_type),
        title=title.strip(),
        authors=authors,
        publication_date=publication_date,
        identifier=identifier,
        publisher_venue=publisher_venue,
        acknowledgement_note=acknowledgement_note,
        relation_note=relation_note,
        status=OutputStatus.gonderildi,
    )
    db.add(output)
    db.flush()

    # Dosya yükle
    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1]
        safe_name = f"{uuid.uuid4().hex}{ext}"
        dest_dir = os.path.join(settings.upload_dir, str(output.id))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, safe_name)
        with open(dest_path, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        att = Attachment(
            output_id=output.id,
            filename=safe_name,
            original_filename=f.filename,
            file_path=dest_path,
            mime_type=f.content_type,
        )
        db.add(att)

    db.commit()
    return RedirectResponse(f"/portal/proje/{project_id}?success=1", status_code=302)


@router.get("/cikti/{output_id}/duzenle", response_class=HTMLResponse)
async def edit_output_form(
    output_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output or output.submitted_by_id != user.id:
        raise HTTPException(403)
    if output.status != OutputStatus.revize_istendi:
        raise HTTPException(400, "Yalnızca revize istenen çıktılar düzenlenebilir.")
    return templates.TemplateResponse("faculty/edit_output.html", {
        "request": request, "user": user,
        "output": output, "output_types": OutputType,
    })


@router.post("/cikti/{output_id}/duzenle")
async def edit_output_submit(
    output_id: int,
    output_type: str = Form(...),
    title: str = Form(...),
    authors: Optional[str] = Form(None),
    publication_date: Optional[str] = Form(None),
    identifier: Optional[str] = Form(None),
    publisher_venue: Optional[str] = Form(None),
    acknowledgement_note: Optional[str] = Form(None),
    relation_note: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output or output.submitted_by_id != user.id:
        raise HTTPException(403)
    if output.status != OutputStatus.revize_istendi:
        raise HTTPException(400, "Yalnızca revize istenen çıktılar düzenlenebilir.")

    output.output_type = OutputType(output_type)
    output.title = title.strip()
    output.authors = authors
    output.publication_date = publication_date
    output.identifier = identifier
    output.publisher_venue = publisher_venue
    output.acknowledgement_note = acknowledgement_note
    output.relation_note = relation_note
    output.status = OutputStatus.gonderildi
    output.admin_note = None

    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1]
        safe_name = f"{uuid.uuid4().hex}{ext}"
        dest_dir = os.path.join(settings.upload_dir, str(output.id))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, safe_name)
        with open(dest_path, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        att = Attachment(
            output_id=output.id,
            filename=safe_name,
            original_filename=f.filename,
            file_path=dest_path,
            mime_type=f.content_type,
        )
        db.add(att)

    db.commit()
    return RedirectResponse(f"/portal/proje/{output.project_id}?revised=1", status_code=302)


@router.post("/proje/{project_id}/cikti-yok")
async def declare_no_output(
    project_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404)
    _check_project_access(user, project)
    project.no_output_declared = True
    db.commit()
    return RedirectResponse(f"/portal/proje/{project_id}?no_output=1", status_code=302)


@router.post("/proje/{project_id}/cikti-yok-kaldir")
async def undeclare_no_output(
    project_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404)
    _check_project_access(user, project)
    project.no_output_declared = False
    db.commit()
    return RedirectResponse(f"/portal/proje/{project_id}", status_code=302)


@router.get("/cikti/{output_id}/sil")
async def delete_output(
    output_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    output = db.query(Output).filter(Output.id == output_id).first()
    if not output or output.submitted_by_id != user.id:
        raise HTTPException(403)
    if output.status == OutputStatus.onaylandi:
        raise HTTPException(400, "Onaylanan çıktılar silinemez.")
    project_id = output.project_id
    db.delete(output)
    db.commit()
    return RedirectResponse(f"/portal/proje/{project_id}", status_code=302)


def _check_project_access(user: User, project: Project):
    if user.role.value == "admin":
        return
    ids = {p.id for p in user.led_projects + user.research_projects}
    if project.id not in ids:
        raise HTTPException(403, "Bu projeye erişim yetkiniz yok.")
