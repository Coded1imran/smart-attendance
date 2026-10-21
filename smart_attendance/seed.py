"""
Seed Script for Smart Attendance (AttendAI)
Populates initial sample lecturers, students, courses, and active sessions matching the UI mockups.
"""
import sys
import os
import secrets
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import init_db, SessionLocal
from app.models import User, UserRole, Course, Enrollment, AttendanceSession, AttendanceRecord, AttendanceStatus
from app.auth import hash_password
from app.utils import get_rotating_code_data
from app.config import settings

def run_seed():
    init_db()
    db = SessionLocal()

    print("Checking existing seed data...")
    if db.query(User).filter(User.email == "dr.bello@university.edu").first():
        print("Database already seeded.")
        db.close()
        return

    print("Seeding demo accounts...")
    # 1. Lecturer (Dr. Bello)
    lecturer = User(
        full_name="Dr. Bello Usman",
        email="dr.bello@university.edu",
        password_hash=hash_password("password123"),
        role=UserRole.LECTURER,
        staff_id="STF/2024/01",
        consent_given=True
    )
    db.add(lecturer)

    # 2. Students
    # Generate synthetic 128-d face embedding
    sample_embedding = [0.088] * 128

    student1 = User(
        full_name="Ahmed Musa",
        email="ahmed.musa@student.edu",
        password_hash=hash_password("password123"),
        role=UserRole.STUDENT,
        matric_no="U/2021/001",
        consent_given=True
    )
    student1.set_embedding_list(sample_embedding)
    db.add(student1)

    student2 = User(
        full_name="Fatima Ali",
        email="fatima.ali@student.edu",
        password_hash=hash_password("password123"),
        role=UserRole.STUDENT,
        matric_no="U/2021/002",
        consent_given=True
    )
    student2.set_embedding_list(sample_embedding)
    db.add(student2)

    student3 = User(
        full_name="Usman Ibrahim",
        email="usman.ibrahim@student.edu",
        password_hash=hash_password("password123"),
        role=UserRole.STUDENT,
        matric_no="U/2021/028",
        consent_given=True
    )
    student3.set_embedding_list(sample_embedding)
    db.add(student3)

    db.commit()

    print("Seeding courses...")
    # 3. Courses
    c1 = Course(code="CS101", title="Introduction to Computer Science", lecturer_id=lecturer.id)
    c2 = Course(code="MAT202", title="Discrete Mathematics", lecturer_id=lecturer.id)
    c3 = Course(code="PHY101", title="Physics Basics", lecturer_id=lecturer.id)
    db.add_all([c1, c2, c3])
    db.commit()

    print("Enrolling students...")
    # 4. Enrollments
    e1 = Enrollment(student_id=student1.id, course_id=c1.id)
    e2 = Enrollment(student_id=student1.id, course_id=c2.id)
    e3 = Enrollment(student_id=student1.id, course_id=c3.id)

    e4 = Enrollment(student_id=student2.id, course_id=c1.id)
    e5 = Enrollment(student_id=student3.id, course_id=c1.id)
    db.add_all([e1, e2, e3, e4, e5])
    db.commit()

    print("Opening active attendance session for CS101...")
    # 5. Active Attendance Session for CS101 (Abuja coordinates: 9.0765, 7.3986)
    now = datetime.now(timezone.utc)
    seed = secrets.token_hex(32)
    code, _ = get_rotating_code_data(seed, settings.ROTATING_CODE_INTERVAL_SECONDS)

    session = AttendanceSession(
        course_id=c1.id,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(minutes=60),
        secret_seed=seed,
        rotating_code=code,
        latitude=9.0765,
        longitude=7.3986,
        radius_meters=50.0,
        is_open=True
    )
    db.add(session)
    db.commit()

    print("Adding historical records...")
    # 6. Sample Records
    r1 = AttendanceRecord(
        session_id=session.id,
        student_id=student2.id,
        timestamp=now - timedelta(minutes=3),
        status=AttendanceStatus.PRESENT,
        verification_score=98.5,
        distance_meters=14.2,
        liveness_passed=True,
        flagged=False
    )
    r2 = AttendanceRecord(
        session_id=session.id,
        student_id=student3.id,
        timestamp=now - timedelta(minutes=1),
        status=AttendanceStatus.PENDING_REVIEW,
        verification_score=70.1,
        distance_meters=62.0,
        liveness_passed=True,
        flagged=True,
        flag_reason="Face similarity low (70.1%) and location slightly outside radius (62m)"
    )
    db.add_all([r1, r2])
    db.commit()
    db.close()

    print("\n✅ Database seeded successfully with demo hackathon data!")
    print("-------------------------------------------------------")
    print("Lecturer login:  dr.bello@university.edu  / password123")
    print("Student login:   ahmed.musa@student.edu   / password123")
    print("-------------------------------------------------------\n")

if __name__ == "__main__":
    run_seed()
