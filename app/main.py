import os
from pathlib import Path
from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.config import settings
from app.database import init_db
from app.routers import auth_routes, lecturer_routes, student_routes

# Initialize FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-Powered Anti-Proxy Attendance Management System (AttendAI)",
    version="1.0.0"
)

# Base directories
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Mount Static Assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount Routers
app.include_router(auth_routes.router)
app.include_router(lecturer_routes.router)
app.include_router(student_routes.router)

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@app.on_event("startup")
def on_startup():
    """Ensure database tables exist on server startup."""
    init_db()

@app.exception_handler(status.HTTP_401_UNAUTHORIZED)
async def unauthorized_handler(request: Request, exc):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return JSONResponse(status_code=401, content={"detail": "Authentication required."})

@app.exception_handler(status.HTTP_403_FORBIDDEN)
async def forbidden_handler(request: Request, exc):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return templates.TemplateResponse(
            request=request,
            name="components/error.html",
            context={
                "status_code": 403,
                "title": "Access Denied",
                "message": str(exc.detail) if hasattr(exc, "detail") else "You do not have permission to view this page."
            },
            status_code=403
        )
    return JSONResponse(
        status_code=403,
        content={"detail": str(exc.detail) if hasattr(exc, "detail") else "Access forbidden."}
    )
