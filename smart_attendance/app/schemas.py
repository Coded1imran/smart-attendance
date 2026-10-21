from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator

# ----------------- Auth & Registration Schemas ----------------- #

class StudentRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120, description="Student's full legal name")
    email: EmailStr = Field(..., description="Student's institutional or personal email")
    password: str = Field(..., min_length=6, max_length=100, description="Account password")
    matric_no: str = Field(..., min_length=2, max_length=50, description="Unique matriculation number")
    consent_given: bool = Field(..., description="Consent to biometric face feature extraction")
    face_image_base64: str = Field(..., description="Base64 encoded webcam selfie snapshot")

    @field_validator("consent_given")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent must be accepted for face verification.")
        return v


class LecturerRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120, description="Lecturer's full name")
    email: EmailStr = Field(..., description="Lecturer's email address")
    password: str = Field(..., min_length=6, max_length=100, description="Account password")
    staff_id: str = Field(..., min_length=2, max_length=50, description="Lecturer's staff identification number")
    consent_given: bool = Field(True, description="Consent agreement")

    @field_validator("consent_given")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent must be given to create an account.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: str = Field(..., pattern="^(student|lecturer)$", description="Role: 'student' or 'lecturer'")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str
    email: str


# ----------------- Course Schemas ----------------- #

class CourseCreateRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=30, description="Course code, e.g. CS101")
    title: str = Field(..., min_length=3, max_length=200, description="Course title, e.g. Introduction to Computer Science")


class CourseResponse(BaseModel):
    id: int
    code: str
    title: str
    lecturer_name: str
    student_count: int = 0
    active_session_id: Optional[int] = None

    class Config:
        from_attributes = True


class CourseEnrollRequest(BaseModel):
    course_id: int


# ----------------- Attendance Session Schemas ----------------- #

class SessionCreateRequest(BaseModel):
    course_id: int
    duration_minutes: int = Field(15, ge=1, le=240, description="Session lifespan in minutes")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Classroom latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Classroom longitude")
    radius_meters: float = Field(50.0, ge=5.0, le=500.0, description="Geofence radius in meters")


class SessionResponse(BaseModel):
    id: int
    course_id: int
    course_code: str
    course_title: str
    start_time: str
    end_time: str
    rotating_code: str
    seconds_remaining: int
    latitude: float
    longitude: float
    radius_meters: float
    is_open: bool

    class Config:
        from_attributes = True


# ----------------- Anti-Proxy Verification Schemas ----------------- #

class MarkAttendanceRequest(BaseModel):
    session_id: int
    rotating_code: str = Field(..., min_length=6, max_length=6, description="6-digit live classroom code")
    latitude: float = Field(..., description="Student's browser GPS latitude")
    longitude: float = Field(..., description="Student's browser GPS longitude")
    face_image_base64: str = Field(..., description="Live webcam selfie capture (base64)")
    liveness_passed: bool = Field(..., description="Whether client/server liveness challenge passed")
    challenge_type: Optional[str] = Field("blink", description="Type of challenge: 'blink' or 'head_turn'")


class AttendanceRecordResponse(BaseModel):
    id: int
    session_id: int
    student_id: int
    student_name: str
    matric_no: str
    course_code: str
    date: str
    time: str
    status: str
    verification_score: float
    distance_meters: float
    liveness_passed: bool
    flagged: bool
    flag_reason: Optional[str] = None

    class Config:
        from_attributes = True


class RecordReviewRequest(BaseModel):
    status: str = Field(..., pattern="^(Present|Rejected)$", description="Approved status: 'Present' or 'Rejected'")
    flag_reason: Optional[str] = None
