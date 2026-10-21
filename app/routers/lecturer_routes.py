import secrets
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
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
from app.schemas import (
    CourseCreateRequest,
    SessionCreateRequest,
    RecordReviewRequest
)
from app.auth import get_current_lecturer
from app.utils import get_rotating_code_data, calculate_haversine_distance
from app.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/lecturer", tags=["Lecturer"])


# ----------------- Lecturer Page Views ----------------- #

@router.get("/dashboard", response_class=HTMLResponse)
def lecturer_dashboard_view(
    request: Request,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """
    Screen 7: Lecturer Dashboard
    Displays:
    - Total Courses created
    - Active attendance sessions count
    - Total enrolled students across courses
    - Recent Attendance (Live) records feed
    """
    # 1. Total Courses
    courses = db.query(Course).filter(Course.lecturer_id == lecturer.id).all()
    course_ids = [c.id for c in courses]
    total_courses = len(courses)

    # 2. Total Students enrolled across all lecturer's courses
    total_students = (
        db.query(func.count(func.distinct(Enrollment.student_id)))
        .filter(Enrollment.course_id.in_(course_ids))
        .scalar()
        if course_ids else 0
    )

    # 3. Active Sessions
    now = datetime.now(timezone.utc)
    active_sessions = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.course_id.in_(course_ids),
            AttendanceSession.is_open == True,
            AttendanceSession.start_time <= now,
            AttendanceSession.end_time >= now
        )
        .all()
        if course_ids else []
    )
    active_sessions_count = len(active_sessions)

    # 4. Recent Attendance records
    recent_records = (
        db.query(AttendanceRecord)
        .join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id)
        .filter(AttendanceSession.course_id.in_(course_ids))
        .order_by(desc(AttendanceRecord.timestamp))
        .limit(10)
        .all()
        if course_ids else []
    )

    return templates.TemplateResponse(
        request=request,
        name="lecturer_dashboard.html",
        context={
            "lecturer": lecturer,
            "total_courses": total_courses,
            "active_sessions_count": active_sessions_count,
            "total_students": total_students,
            "recent_records": recent_records,
            "courses": courses,
            "active_sessions": active_sessions
        }
    )


@router.get("/sessions/create", response_class=HTMLResponse)
def create_session_view(
    request: Request,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """
    Screen 8: Start Attendance Session Page
    Allows setting course, duration, classroom GPS location, and radius.
    Displays rotating 6-digit classroom code preview.
    """
    courses = db.query(Course).filter(Course.lecturer_id == lecturer.id).all()
    return templates.TemplateResponse(
        request=request,
        name="create_session.html",
        context={
            "lecturer": lecturer,
            "courses": courses
        }
    )


@router.get("/sessions/{session_id}/live", response_class=HTMLResponse)
def live_attendance_view(
    session_id: int,
    request: Request,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """
    Screen 9: Live Attendance List (e.g. Live Attendance - CS101)
    Shows real-time table of attendees, verification scores, flagged items,
    and review modal triggers.
    """
    session_obj = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session_obj or session_obj.course.lecturer_id != lecturer.id:
        raise HTTPException(status_code=404, detail="Attendance session not found.")

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == session_id)
        .order_by(desc(AttendanceRecord.timestamp))
        .all()
    )

    code, seconds_remaining = get_rotating_code_data(session_obj.secret_seed, settings.ROTATING_CODE_INTERVAL_SECONDS)

    return templates.TemplateResponse(
        request=request,
        name="live_attendance.html",
        context={
            "lecturer": lecturer,
            "session": session_obj,
            "course": session_obj.course,
            "records": records,
            "current_code": code,
            "seconds_remaining": seconds_remaining
        }
    )


# ----------------- Lecturer Action APIs ----------------- #

@router.post("/courses")
def create_course(
    payload: CourseCreateRequest,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """Creates a new course taught by the lecturer."""
    clean_code = payload.code.strip().upper()
    existing = db.query(Course).filter(Course.code == clean_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Course with code {clean_code} already exists.")

    new_course = Course(
        code=clean_code,
        title=payload.title.strip(),
        lecturer_id=lecturer.id
    )
    db.add(new_course)
    db.commit()
    db.refresh(new_course)

    return {
        "status": "success",
        "message": f"Course {new_course.code} created successfully.",
        "course": {
            "id": new_course.id,
            "code": new_course.code,
            "title": new_course.title
        }
    }


@router.post("/sessions/create")
def start_attendance_session(
    payload: SessionCreateRequest,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """
    Opens an attendance session:
    - Generates cryptographic secret seed for rotating 30s code.
    - Saves classroom GPS location and geofence radius.
    - Sets duration window.
    """
    course = db.query(Course).filter(Course.id == payload.course_id, Course.lecturer_id == lecturer.id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found or unauthorized.")

    # Close any existing active session for this course
    now = datetime.now(timezone.utc)
    db.query(AttendanceSession).filter(
        AttendanceSession.course_id == course.id,
        AttendanceSession.is_open == True
    ).update({"is_open": False})

    # Generate cryptographic seed for rotating code
    seed = secrets.token_hex(32)
    current_code, _ = get_rotating_code_data(seed, settings.ROTATING_CODE_INTERVAL_SECONDS)

    start_time = now
    end_time = now + timedelta(minutes=payload.duration_minutes)

    new_session = AttendanceSession(
        course_id=course.id,
        start_time=start_time,
        end_time=end_time,
        secret_seed=seed,
        rotating_code=current_code,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
        is_open=True
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "status": "success",
        "message": "Attendance session started.",
        "session_id": new_session.id,
        "rotating_code": current_code,
        "redirect_url": f"/lecturer/sessions/{new_session.id}/live"
    }


@router.get("/api/sessions/{session_id}/code")
def get_session_live_code(
    session_id: int,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """
    Returns the current rotating 6-digit code and seconds remaining for classroom display.
    Rotates every 30 seconds.
    """
    session_obj = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session_obj or session_obj.course.lecturer_id != lecturer.id:
        raise HTTPException(status_code=404, detail="Session not found.")

    code, seconds_remaining = get_rotating_code_data(session_obj.secret_seed, settings.ROTATING_CODE_INTERVAL_SECONDS)
    
    # Update cache on session model
    session_obj.rotating_code = code
    db.commit()

    return {
        "rotating_code": code,
        "seconds_remaining": seconds_remaining,
        "is_active": session_obj.is_currently_active()
    }


@router.get("/api/sessions/{session_id}/records")
def get_session_records_api(
    session_id: int,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """
    Polling / real-time feed endpoint (called every 5 seconds by the live attendance screen).
    Returns all attendance records for this session with student info, verification scores, and flags.
    """
    session_obj = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session_obj or session_obj.course.lecturer_id != lecturer.id:
        raise HTTPException(status_code=404, detail="Session not found.")

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == session_id)
        .order_by(desc(AttendanceRecord.timestamp))
        .all()
    )

    data = []
    for r in records:
        ts = r.timestamp if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc)
        data.append({
            "id": r.id,
            "student_name": r.student.full_name,
            "matric_no": r.student.matric_no,
            "date": ts.strftime("%Y-%m-%d"),
            "time": ts.strftime("%I:%M:%S %p"),
            "status": r.status,
            "verification_score": r.verification_score,
            "distance_meters": r.distance_meters,
            "flagged": r.flagged,
            "flag_reason": r.flag_reason
        })

    return {
        "status": "success",
        "count": len(data),
        "is_active": session_obj.is_currently_active(),
        "records": data
    }


@router.post("/api/records/{record_id}/review")
def review_flagged_record(
    record_id: int,
    payload: RecordReviewRequest,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """
    Screen 11: Flagged Record Review Modal Action
    Allows lecturer to override / approve or reject a flagged attendance entry.
    """
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == record_id).first()
    if not record or record.session.course.lecturer_id != lecturer.id:
        raise HTTPException(status_code=404, detail="Attendance record not found.")

    record.status = payload.status
    if payload.status == AttendanceStatus.PRESENT:
        record.flagged = False
        record.flag_reason = f"Approved by lecturer on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
    else:
        record.flagged = True
        record.flag_reason = payload.flag_reason or f"Rejected by lecturer on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"

    db.commit()
    db.refresh(record)

    return {
        "status": "success",
        "message": f"Attendance record marked as {record.status}.",
        "record_id": record.id,
        "new_status": record.status
    }


@router.post("/sessions/{session_id}/close")
def close_session(
    session_id: int,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """Closes an active attendance session manually."""
    session_obj = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session_obj or session_obj.course.lecturer_id != lecturer.id:
        raise HTTPException(status_code=404, detail="Session not found.")

    session_obj.is_open = False
    db.commit()

    return {"status": "success", "message": "Attendance session closed."}


@router.get("/sessions/{session_id}/export")
def export_attendance_csv(
    session_id: int,
    lecturer: User = Depends(get_current_lecturer),
    db: Session = Depends(get_db)
):
    """
    Exports attendance records for a session as a downloadable RFC 4180 CSV file.
    """
    session_obj = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session_obj or session_obj.course.lecturer_id != lecturer.id:
        raise HTTPException(status_code=404, detail="Session not found.")

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == session_id)
        .order_by(AttendanceRecord.timestamp.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Student Name",
        "Matric No",
        "Course Code",
        "Course Title",
        "Date",
        "Time",
        "Status",
        "Verification Score (%)",
        "Distance (m)",
        "Liveness Passed",
        "Flagged",
        "Flag Reason"
    ])

    for r in records:
        ts = r.timestamp if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc)
        writer.writerow([
            r.student.full_name,
            r.student.matric_no,
            session_obj.course.code,
            session_obj.course.title,
            ts.strftime("%Y-%m-%d"),
            ts.strftime("%I:%M:%S %p"),
            r.status,
            f"{r.verification_score:.1f}%",
            f"{r.distance_meters:.1f}",
            "Yes" if r.liveness_passed else "No",
            "Yes" if r.flagged else "No",
            r.flag_reason or ""
        ])

    output.seek(0)
    filename = f"Attendance_{session_obj.course.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
