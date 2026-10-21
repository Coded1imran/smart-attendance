import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User, UserRole

COOKIE_NAME = "access_token"

def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed JWT access token containing user identity and role claims."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decodes and validates a JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def get_token_from_request(request: Request) -> Optional[str]:
    """Extracts JWT token from either the Authorization Bearer header or the HTTP-only cookie."""
    # 1. Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    
    # 2. HTTP cookie (for seamless Jinja2 browser page loads)
    token = request.cookies.get(COOKIE_NAME)
    if token:
        if token.startswith("Bearer "):
            return token.split(" ", 1)[1].strip()
        return token
    
    return None


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Retrieves current authenticated user if token is valid, otherwise returns None."""
    token = get_token_from_request(request)
    if not token:
        return None
    
    payload = decode_access_token(token)
    if not payload:
        return None
    
    email: str = payload.get("sub")
    if not email:
        return None
    
    return db.query(User).filter(User.email == email).first()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Enforces authentication. Raises 401 if unauthenticated."""
    user = get_current_user_optional(request, db)
    if not user:
        # Check if browser HTML request vs JSON API call
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": "/login"}
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(required_role: str):
    """Factory dependency that strictly enforces role-based access control (RBAC)."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires {required_role} privileges."
            )
        return current_user
    return role_checker


# Convenient role dependencies
get_current_student = require_role(UserRole.STUDENT)
get_current_lecturer = require_role(UserRole.LECTURER)
