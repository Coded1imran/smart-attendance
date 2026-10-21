import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class UserRole:
    STUDENT = "student"
    LECTURER = "lecturer"

class AttendanceStatus:
    PRESENT = "Present"
    PENDING_REVIEW = "Pending Review"
    REJECTED = "Rejected"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False) # 'student' or 'lecturer'
    
    # Role-specific identity numbers
    matric_no = Column(String(50), unique=True, index=True, nullable=True) # for students
    staff_id = Column(String(50), unique=True, index=True, nullable=True)   # for lecturers
    
    # Store ONLY mathematical face embedding vector (JSON-encoded list of floats); Never store raw image
    face_embedding = Column(Text, nullable=True)
    consent_given = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    courses_taught = relationship("Course", back_populates="lecturer", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="student", cascade="all, delete-orphan")
    attendance_records = relationship("AttendanceRecord", back_populates="student", cascade="all, delete-orphan")

    def get_embedding_list(self):
        """Helper to safely parse stored JSON face embedding vector."""
        if not self.face_embedding:
            return None
        try:
            return json.loads(self.face_embedding)
        except Exception:
            return None

    def set_embedding_list(self, embedding: list):
        """Helper to serialize face embedding vector to JSON string."""
        self.face_embedding = json.dumps(embedding) if embedding else None

    @property
    def display_id(self) -> str:
        """Returns matric_no for students or staff_id for lecturers."""
        return self.matric_no if self.role == UserRole.STUDENT else (self.staff_id or "")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False) # e.g. "CS101"
    title = Column(String(200), nullable=False)                         # e.g. "Introduction to Computer Science"
    lecturer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    lecturer = relationship("User", back_populates="courses_taught")
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")
    sessions = relationship("AttendanceSession", back_populates="course", cascade="all, delete-orphan")


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Prevent a student from enrolling twice in the same course
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )

    # Relationships
    student = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Secret seed used to deterministically compute rotating TOTP-like 6-digit codes
    secret_seed = Column(String(64), nullable=False)
    rotating_code = Column(String(6), nullable=False) # Current 6-digit classroom display code
    
    # GPS Geo-fencing coordinates
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius_meters = Column(Float, default=50.0, nullable=False)
    
    is_open = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    course = relationship("Course", back_populates="sessions")
    records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")

    def is_currently_active(self) -> bool:
        """Evaluates whether session is open and within its temporal window."""
        now = datetime.now(timezone.utc)
        start = self.start_time if self.start_time.tzinfo else self.start_time.replace(tzinfo=timezone.utc)
        end = self.end_time if self.end_time.tzinfo else self.end_time.replace(tzinfo=timezone.utc)
        return self.is_open and (start <= now <= end)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Verification and Status
    status = Column(String(30), default=AttendanceStatus.PENDING_REVIEW, nullable=False)
    verification_score = Column(Float, default=0.0, nullable=False) # e.g. 96.5 (% similarity)
    distance_meters = Column(Float, default=0.0, nullable=False)
    liveness_passed = Column(Boolean, default=False, nullable=False)
    flagged = Column(Boolean, default=False, nullable=False)
    flag_reason = Column(Text, nullable=True)

    # Core requirement: Prevent duplicate attendance for the same session!
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_student"),
    )

    # Relationships
    session = relationship("AttendanceSession", back_populates="records")
    student = relationship("User", back_populates="attendance_records")
