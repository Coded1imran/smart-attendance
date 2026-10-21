from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from app.database import get_db
from app.models import User, UserRole
from app.schemas import StudentRegisterRequest, LecturerRegisterRequest, LoginRequest
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user_optional,
    get_current_user,
    COOKIE_NAME
)
from app.ai.face_engine import extract_face_embedding

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Authentication"])


# ----------------- Page Renderers (Jinja2) ----------------- #

@router.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)):
    """Screen 1: AttendAI Landing Page"""
    user = get_current_user_optional(request, db)
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user})


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    """Screen 4: Role-selector Login Page (Student vs Lecturer)"""
    user = get_current_user_optional(request, db)
    if user:
        if user.role == UserRole.STUDENT:
            return RedirectResponse(url="/student/dashboard", status_code=303)
        return RedirectResponse(url="/lecturer/dashboard", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.get("/register/student", response_class=HTMLResponse)
def register_student_page(request: Request, db: Session = Depends(get_db)):
    """Screen 2: Student Registration Page with live webcam capture"""
    user = get_current_user_optional(request, db)
    if user and user.role == UserRole.STUDENT:
        return RedirectResponse(url="/student/dashboard", status_code=303)
    return templates.TemplateResponse(request=request, name="register_student.html", context={})


@router.get("/register/lecturer", response_class=HTMLResponse)
def register_lecturer_page(request: Request, db: Session = Depends(get_db)):
    """Screen 3: Lecturer Registration Page"""
    user = get_current_user_optional(request, db)
    if user and user.role == UserRole.LECTURER:
        return RedirectResponse(url="/lecturer/dashboard", status_code=303)
    return templates.TemplateResponse(request=request, name="register_lecturer.html", context={})


# ----------------- API Endpoints ----------------- #

@router.post("/auth/login")
async def login_api(
    response: Response,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Validates user credentials and role.
    Issues JWT access token and sets secure HTTP-only cookie.
    """
    user = db.query(User).filter(User.email == login_data.email.strip().lower()).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    if user.role != login_data.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This account is not registered as a {login_data.role}. Please select the '{user.role.title()}' option."
        )

    # Generate JWT token
    token = create_access_token(data={"sub": user.email, "role": user.role, "name": user.full_name})

    # Set HTTP-only cookie for web navigation
    redirect_url = "/student/dashboard" if user.role == UserRole.STUDENT else "/lecturer/dashboard"
    res = JSONResponse(content={
        "status": "success",
        "message": f"Welcome back, {user.full_name}!",
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "redirect_url": redirect_url
    })
    res.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7
    )
    return res


@router.post("/auth/register/student")
async def register_student_api(
    payload: StudentRegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Registers a student:
    1. Validates unique email and matric_no.
    2. Validates consent agreement.
    3. Extracts face embedding from webcam snapshot.
    4. PRIVACY GUARANTEE: Never stores raw image file; only stores float vector.
    5. Sets session and logs student in.
    """
    email_clean = payload.email.strip().lower()
    matric_clean = payload.matric_no.strip().upper()

    if db.query(User).filter(User.email == email_clean).first():
        raise HTTPException(status_code=400, detail="A user with this email already exists.")
    
    if db.query(User).filter(User.matric_no == matric_clean).first():
        raise HTTPException(status_code=400, detail="A student with this Matric Number is already registered.")

    if not payload.consent_given:
        raise HTTPException(status_code=400, detail="Consent is required for facial biometric registration.")

    # Extract Face Embedding
    try:
        embedding = extract_face_embedding(payload.face_image_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process face photo: {str(e)}. Please position your face clearly in the frame.")

    # Create new student record
    new_user = User(
        full_name=payload.full_name.strip(),
        email=email_clean,
        password_hash=hash_password(payload.password),
        role=UserRole.STUDENT,
        matric_no=matric_clean,
        consent_given=True
    )
    new_user.set_embedding_list(embedding)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Issue token
    token = create_access_token(data={"sub": new_user.email, "role": new_user.role, "name": new_user.full_name})
    res = JSONResponse(content={
        "status": "success",
        "message": "Student registration successful!",
        "access_token": token,
        "redirect_url": "/student/dashboard"
    })
    res.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7
    )
    return res


@router.post("/auth/register/lecturer")
async def register_lecturer_api(
    payload: LecturerRegisterRequest,
    db: Session = Depends(get_db)
):
    """Registers a lecturer with staff ID and password."""
    email_clean = payload.email.strip().lower()
    staff_clean = payload.staff_id.strip().upper()

    if db.query(User).filter(User.email == email_clean).first():
        raise HTTPException(status_code=400, detail="A user with this email already exists.")
    
    if db.query(User).filter(User.staff_id == staff_clean).first():
        raise HTTPException(status_code=400, detail="A lecturer with this Staff ID is already registered.")

    new_user = User(
        full_name=payload.full_name.strip(),
        email=email_clean,
        password_hash=hash_password(payload.password),
        role=UserRole.LECTURER,
        staff_id=staff_clean,
        consent_given=payload.consent_given
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(data={"sub": new_user.email, "role": new_user.role, "name": new_user.full_name})
    res = JSONResponse(content={
        "status": "success",
        "message": "Lecturer registration successful!",
        "access_token": token,
        "redirect_url": "/lecturer/dashboard"
    })
    res.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7
    )
    return res


@router.get("/logout")
def logout(response: Response):
    """Clears authentication session cookie and redirects to login."""
    res = RedirectResponse(url="/login", status_code=303)
    res.delete_cookie(COOKIE_NAME)
    return res


@router.get("/auth/me")
def get_current_user_profile(user: User = Depends(get_current_user)):
    """Returns profile information for the authenticated user."""
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "identifier": user.display_id,
        "has_face_enrolled": user.face_embedding is not None,
        "consent_given": user.consent_given
    }
