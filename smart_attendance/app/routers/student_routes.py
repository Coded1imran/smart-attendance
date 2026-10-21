from datetime import datetime, timezone
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.database import get_db
from app.models import (
    User,
    UserRole,
    Course,
    Enrollment,
    AttendanceSession,
    AttendanceRecord,
    AttendanceStatus
)
from app.schemas import CourseEnrollRequest, MarkAttendanceRequest
from app.auth import get_current_student
from app.utils import calculate_haversine_distance, verify_rotating_code
from app.ai.face_engine import extract_face_embedding, compute_similarity
from app.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/student", tags=["Student"])


# ----------------- Student Page Views ----------------- #

@router.get("/dashboard", response_class=HTMLResponse)
def student_dashboard_view(
    request: Request,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    Screen 5: Student Dashboard
    Displays:
    - Enrolled Courses count
    - Overall Attendance percentage
    - Total Sessions recorded
    - My Courses cards with course-level attendance % and active session status
    - Recent Attendance table
    """
    # 1. Enrolled Courses
    enrollments = db.query(Enrollment).filter(Enrollment.student_id == student.id).all()
    enrolled_course_ids = [e.course_id for e in enrollments]
    total_enrolled_courses = len(enrolled_course_ids)

    # 2. Total Sessions & Attendance Records
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student.id)
        .order_by(desc(AttendanceRecord.timestamp))
        .all()
    )
    total_sessions_recorded = len(records)
    present_count = sum(1 for r in records if r.status == AttendanceStatus.PRESENT)
    overall_percentage = (
        round((present_count / total_sessions_recorded) * 100, 1)
        if total_sessions_recorded > 0 else 100.0
    )

    # 3. Active sessions currently open for enrolled courses
    now = datetime.now(timezone.utc)
    active_sessions = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.course_id.in_(enrolled_course_ids),
            AttendanceSession.is_open == True,
            AttendanceSession.start_time <= now,
            AttendanceSession.end_time >= now
        )
        .all()
        if enrolled_course_ids else []
    )
    active_course_session_map = {s.course_id: s.id for s in active_sessions}

    # 4. Course Cards Details (with course-level attendance %)
    courses_data = []
    for enr in enrollments:
        c = enr.course
        course_records = [r for r in records if r.session.course_id == c.id]
        c_total = len(course_records)
        c_present = sum(1 for r in course_records if r.status == AttendanceStatus.PRESENT)
        c_pct = round((c_present / c_total) * 100) if c_total > 0 else 100
        courses_data.append({
            "id": c.id,
            "code": c.code,
            "title": c.title,
            "attendance_pct": c_pct,
            "active_session_id": active_course_session_map.get(c.id)
        })

    return templates.TemplateResponse(
        request=request,
        name="student_dashboard.html",
        context={
            "student": student,
            "total_enrolled": total_enrolled_courses,
            "overall_percentage": int(overall_percentage),
            "total_sessions": total_sessions_recorded,
            "my_courses": courses_data,
            "recent_records": records[:5]
        }
    )


@router.get("/courses", response_class=HTMLResponse)
def student_courses_view(
    request: Request,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """Lists all available courses and current enrollment statuses."""
    all_courses = db.query(Course).all()
    enrolled_ids = {e.course_id for e in student.enrollments}

    courses_list = []
    for c in all_courses:
        courses_list.append({
            "id": c.id,
            "code": c.code,
            "title": c.title,
            "lecturer_name": c.lecturer.full_name,
            "is_enrolled": c.id in enrolled_ids
        })

    return templates.TemplateResponse(
        request=request,
        name="student_courses.html",
        context={
            "student": student,
            "courses": courses_list
        }
    )


@router.get("/mark-attendance", response_class=HTMLResponse)
def mark_attendance_view(
    request: Request,
    session_id: Optional[int] = None,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    Screen 6: Anti-Proxy Verification Wizard
    5-step verification process:
    1. Rotating 6-Digit Code
    2. Geolocation check
    3. MediaPipe Liveness challenge
    4. Face match similarity
    5. Complete confirmation
    """
    # If no session_id provided, pick the first active session for enrolled courses
    enrolled_ids = [e.course_id for e in student.enrollments]
    now = datetime.now(timezone.utc)

    active_sessions = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.course_id.in_(enrolled_ids),
            AttendanceSession.is_open == True,
            AttendanceSession.start_time <= now,
            AttendanceSession.end_time >= now
        )
        .all()
        if enrolled_ids else []
    )

    selected_session = None
    if session_id:
        selected_session = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    elif active_sessions:
        selected_session = active_sessions[0]

    # Check if student already marked attendance for this session
    already_marked = False
    existing_record = None
    if selected_session:
        existing_record = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.session_id == selected_session.id,
                AttendanceRecord.student_id == student.id
            )
            .first()
        )
        if existing_record:
            already_marked = True

    return templates.TemplateResponse(
        request=request,
        name="mark_attendance.html",
        context={
            "student": student,
            "session": selected_session,
            "active_sessions": active_sessions,
            "already_marked": already_marked,
            "existing_record": existing_record
        }
    )


@router.get("/history", response_class=HTMLResponse)
def attendance_history_view(
    request: Request,
    course_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    Screen 10: Attendance History with Course and Date Range filters
    """
    enrollments = db.query(Enrollment).filter(Enrollment.student_id == student.id).all()
    courses = [e.course for e in enrollments]

    query = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student.id)
    )

    if course_id:
        query = query.join(AttendanceSession).filter(AttendanceSession.course_id == course_id)

    records = query.order_by(desc(AttendanceRecord.timestamp)).all()

    # Filter by date range if provided
    filtered_records = []
    for r in records:
        r_date = r.timestamp.strftime("%Y-%m-%d")
        if start_date and r_date < start_date:
            continue
        if end_date and r_date > end_date:
            continue
        filtered_records.append(r)

    total_records = len(filtered_records)
    present_records = sum(1 for r in filtered_records if r.status == AttendanceStatus.PRESENT)
    attendance_pct = round((present_records / total_records) * 100, 1) if total_records > 0 else 100.0

    return templates.TemplateResponse(
        request=request,
        name="attendance_history.html",
        context={
            "student": student,
            "courses": courses,
            "selected_course_id": course_id,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "records": filtered_records,
            "attendance_pct": attendance_pct
        }
    )


# ----------------- Student API Actions ----------------- #

@router.post("/courses/enroll")
def enroll_course(
    payload: CourseEnrollRequest,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """Enrolls the student into a course."""
    course = db.query(Course).filter(Course.id == payload.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    existing = db.query(Enrollment).filter(
        Enrollment.student_id == student.id,
        Enrollment.course_id == payload.course_id
    ).first()

    if existing:
        return {"status": "info", "message": f"Already enrolled in {course.code}."}

    new_enr = Enrollment(student_id=student.id, course_id=course.id)
    db.add(new_enr)
    db.commit()

    return {"status": "success", "message": f"Successfully enrolled in {course.code} - {course.title}."}


@router.post("/api/verify")
def verify_and_mark_attendance(
    payload: MarkAttendanceRequest,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    CORE ANTI-PROXY VERIFICATION FLOW:
    Runs ALL 5 mandatory anti-proxy checks:
    1. Session is open and student is enrolled in the course.
    2. Student enters current rotating 6-digit code.
    3. Browser geolocation is within session radius (Haversine formula).
    4. Live liveness challenge passed (random blink or head-turn).
    5. Live selfie matched against stored face embedding (cosine similarity score).
    
    Decision Logic:
    - All checks pass: status = "Present".
    - Face score borderline (60-74.9%) or location slightly off (+15m buffer):
      status = "Pending Review", flagged = True, flag_reason specified.
    - Code wrong, session expired, or face mismatch (< 60%): rejected.
    - Duplicate prevention: strictly enforced.
    """
    # Check 1: Session open and enrollment
    session_obj = db.query(AttendanceSession).filter(AttendanceSession.id == payload.session_id).first()
    if not session_obj:
        raise HTTPException(status_code=404, detail="Attendance session does not exist.")

    if not session_obj.is_currently_active():
        raise HTTPException(status_code=400, detail="This attendance session has ended or is closed.")

    is_enrolled = db.query(Enrollment).filter(
        Enrollment.student_id == student.id,
        Enrollment.course_id == session_obj.course_id
    ).first()
    if not is_enrolled:
        raise HTTPException(status_code=403, detail="You are not enrolled in this course.")

    # Check for duplicate attendance
    existing_record = db.query(AttendanceRecord).filter(
        AttendanceRecord.session_id == session_obj.id,
        AttendanceRecord.student_id == student.id
    ).first()
    if existing_record:
        raise HTTPException(status_code=400, detail=f"Attendance already marked for this session (Status: {existing_record.status}).")

    # Check 2: Rotating 6-Digit Code
    code_valid = verify_rotating_code(
        payload.rotating_code,
        session_obj.secret_seed,
        settings.ROTATING_CODE_INTERVAL_SECONDS
    )
    if not code_valid:
        raise HTTPException(status_code=400, detail="Invalid or expired rotating code. Please check the classroom screen.")

    # Check 3: Geolocation (Haversine)
    distance_meters = calculate_haversine_distance(
        payload.latitude, payload.longitude,
        session_obj.latitude, session_obj.longitude
    )
    is_within_radius = distance_meters <= session_obj.radius_meters
    is_borderline_location = (
        not is_within_radius and
        distance_meters <= (session_obj.radius_meters + settings.LOCATION_TOLERANCE_METERS)
    )

    if not is_within_radius and not is_borderline_location:
        raise HTTPException(
            status_code=400,
            detail=f"Location verification failed. You are {distance_meters:.1f}m away (allowed: {session_obj.radius_meters}m)."
        )

    # Check 4: Liveness Challenge
    if not payload.liveness_passed:
        raise HTTPException(status_code=400, detail="Liveness verification failed. Real-time human presence could not be confirmed.")

    # Check 5: Live Selfie Face Match
    stored_embedding = student.get_embedding_list()
    if not stored_embedding:
        raise HTTPException(status_code=400, detail="No registered face biometric on file. Please update your profile.")

    try:
        live_embedding = extract_face_embedding(payload.face_image_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Face recognition error: {str(e)}")

    similarity_score = compute_similarity(stored_embedding, live_embedding)

    # Decision Logic Matrix
    flag_reasons = []
    status_result = AttendanceStatus.PRESENT
    flagged = False

    # Check face similarity thresholds
    if similarity_score < settings.FACE_BORDERLINE_THRESHOLD:
        # Outright face mismatch (< 60%)
        # Log attempt as Rejected
        failed_record = AttendanceRecord(
            session_id=session_obj.id,
            student_id=student.id,
            status=AttendanceStatus.REJECTED,
            verification_score=similarity_score,
            distance_meters=distance_meters,
            liveness_passed=payload.liveness_passed,
            flagged=True,
            flag_reason=f"Face mismatch ({similarity_score}% < {settings.FACE_BORDERLINE_THRESHOLD}%)"
        )
        db.add(failed_record)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Face verification failed: Similarity score ({similarity_score}%) is below required threshold."
        )

    elif similarity_score < settings.FACE_SIMILARITY_THRESHOLD:
        # Borderline face match (60% to 74.9%)
        status_result = AttendanceStatus.PENDING_REVIEW
        flagged = True
        flag_reasons.append(f"Borderline face similarity ({similarity_score}%)")

    # Check location borderline
    if is_borderline_location:
        status_result = AttendanceStatus.PENDING_REVIEW
        flagged = True
        flag_reasons.append(f"Location slightly outside radius ({distance_meters:.1f}m > {session_obj.radius_meters}m)")

    # Record attendance
    final_record = AttendanceRecord(
        session_id=session_obj.id,
        student_id=student.id,
        status=status_result,
        verification_score=similarity_score,
        distance_meters=distance_meters,
        liveness_passed=True,
        flagged=flagged,
        flag_reason="; ".join(flag_reasons) if flag_reasons else None
    )
    db.add(final_record)
    db.commit()
    db.refresh(final_record)

    return {
        "status": "success",
        "attendance_status": final_record.status,
        "verification_score": similarity_score,
        "distance_meters": distance_meters,
        "flagged": final_record.flagged,
        "flag_reason": final_record.flag_reason,
        "message": "Attendance successfully recorded!" if final_record.status == AttendanceStatus.PRESENT else "Attendance submitted for lecturer review."
    }
