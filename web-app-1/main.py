"""
=============================================================================
Web Application 1 - Lab Booking System (Port 5000)
Architecture Role: 4. Application Layer (FastAPI + Jinja2)

ปรับปรุงเพื่อความถูกต้องตามสถาปัตยกรรม (Separation of Concerns):
- ลบ Auth Proxy (/auth/login): ให้เป็นหน้าที่ของ Auth Layer (Central Auth) 100%
- ลบ Database Layer (SQLite / init_db / get_db): ให้เป็นหน้าที่ของ Database Layer (Bank)
- Application Layer จัดการเฉพาะ:
  1. Routing & Jinja2 Template Rendering (Home, Booking)
  2. การรับและตรวจสอบความถูกต้องของ JWT Token (AuthN / AuthZ)
  3. Business Logic & Validation (Pydantic Models, Guard Clauses)
  4. In-Memory State & Data Interface สำหรับรอเชื่อมต่อกับ Database Layer
=============================================================================
"""

import os
import time
from typing import Optional, Dict, Any, List

from fastapi import (
    FastAPI,
    Request,
    Cookie,
    Header,
    Depends,
    HTTPException,
    status
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
from dotenv import load_dotenv

# โหลดค่า Environment Variables จากไฟล์ .env
load_dotenv()

# =============================================================================
# ค่าคงที่สำหรับการกำหนดค่าระบบ (Configuration Constants)
# =============================================================================
PORT: int = int(os.getenv("PORT", "5000"))
JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secure-jwt-sso-secret-key-2026")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
COOKIE_NAME: str = os.getenv("COOKIE_NAME", "sso_token")

# ค่าคงที่สำหรับ Business Logic และ Security
ROLE_ADMIN: str = "Admin"
STATUS_AVAILABLE: str = "available"
STATUS_BOOKED: str = "booked"
DEFAULT_TIME_SLOT: str = "13:00 - 16:00"

# =============================================================================
# การระบุโฟลเดอร์สำหรับ Views และ Static Files
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIEWS_SUBDIR = os.path.join(BASE_DIR, "views")
PUBLIC_SUBDIR = os.path.join(BASE_DIR, "public")

TEMPLATES_DIR = VIEWS_SUBDIR if os.path.exists(VIEWS_SUBDIR) else BASE_DIR
PUBLIC_DIR = PUBLIC_SUBDIR if os.path.exists(PUBLIC_SUBDIR) else BASE_DIR

# =============================================================================
# FastAPI Application & Template Initialization
# =============================================================================
app = FastAPI(
    title="Web Application 1 - Lab Booking (Application Layer)",
    description="Lab Booking System - Application Layer (FastAPI + Jinja2)",
    version="2.2.0",
    docs_url="/lab/docs",
    openapi_url="/lab/openapi.json",
    redoc_url="/lab/redoc"
)

security_bearer = HTTPBearer(auto_error=False)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Mount Static Files สำหรับ CSS / Assets
if os.path.exists(PUBLIC_DIR):
    app.mount("/lab/public", StaticFiles(directory=PUBLIC_DIR), name="lab_public")
    app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")


# =============================================================================
# [APPLICATION LAYER: In-Memory Data Store & Interface]
# แยกออกจาก Database Layer (SQLite) โดยสิ้นเชิง:
# ใช้ In-Memory Store สำหรับจำลองข้อมูลเครื่องคอมพิวเตอร์และพร้อมเชื่อมต่อกับ Database Layer
# =============================================================================
INITIAL_COMPUTERS = [
    {"id": "PC-01", "room": "Lab 401 (Networking)", "status": STATUS_AVAILABLE, "bookedBy": None, "time": None},
    {"id": "PC-02", "room": "Lab 401 (Networking)", "status": STATUS_AVAILABLE, "bookedBy": None, "time": None},
    {"id": "PC-03", "room": "Lab 401 (Networking)", "status": STATUS_BOOKED, "bookedBy": "student99", "time": "09:00 - 12:00"},
    {"id": "PC-04", "room": "Lab 402 (Cybersecurity)", "status": STATUS_AVAILABLE, "bookedBy": None, "time": None},
    {"id": "PC-05", "room": "Lab 402 (Cybersecurity)", "status": STATUS_AVAILABLE, "bookedBy": None, "time": None},
    {"id": "PC-06", "room": "Lab 402 (Cybersecurity)", "status": STATUS_AVAILABLE, "bookedBy": None, "time": None}
]

computers_store: List[Dict[str, Any]] = [dict(c) for c in INITIAL_COMPUTERS]


def get_all_computers() -> List[Dict[str, Any]]:
    """ดึงรายการเครื่องคอมพิวเตอร์ทั้งหมด"""
    return [dict(c) for c in computers_store]


def find_computer_by_id(pc_id: str) -> Optional[Dict[str, Any]]:
    """ค้นหาเครื่องคอมพิวเตอร์ตาม ID"""
    for pc in computers_store:
        if pc["id"] == pc_id:
            return pc
    return None


def book_computer_record(pc_id: str, username: str, time_slot: str) -> None:
    """อัปเดตสถานะการจองเครื่องคอมพิวเตอร์"""
    pc = find_computer_by_id(pc_id)
    if pc:
        pc["status"] = STATUS_BOOKED
        pc["bookedBy"] = username
        pc["time"] = time_slot


def cancel_booking_record(pc_id: str) -> None:
    """ยกเลิกการจองและคืนสถานะเครื่องให้ว่าง"""
    pc = find_computer_by_id(pc_id)
    if pc:
        pc["status"] = STATUS_AVAILABLE
        pc["bookedBy"] = None
        pc["time"] = None


# =============================================================================
# Pydantic Request Models
# =============================================================================
class BookRequest(BaseModel):
    computerId: str
    timeSlot: Optional[str] = DEFAULT_TIME_SLOT


class CancelRequest(BaseModel):
    computerId: str


# =============================================================================
# JWT Authentication & Token Utilities (AuthN Helper)
# =============================================================================
def verify_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """ถอดรหัสและตรวจสอบความถูกต้องของ JWT Token ที่ได้รับจาก Auth Layer"""
    if not token:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


def extract_token_from_request(
    sso_cookie: Optional[str] = None,
    bearer: Optional[HTTPAuthorizationCredentials] = None,
    auth_header: Optional[str] = None
) -> Optional[str]:
    """ดึง Token จาก Bearer Credentials, Authorization Header, หรือ SSO Cookie ตามลำดับความสำคัญ"""
    if bearer and bearer.credentials:
        return bearer.credentials
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):]
    if sso_cookie:
        return sso_cookie
    return None


def get_current_user_and_token(
    sso_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    authorization: Optional[str] = Header(default=None)
) -> Dict[str, Any]:
    """FastAPI Dependency สำหรับ Protected Endpoints ตรวจสอบความถูกต้องของ Token"""
    token = extract_token_from_request(sso_token, bearer, authorization)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token or SSO cookie."
        )

    user = verify_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token"
        )

    return {"user": user, "token": token}


# =============================================================================
# Business Logic - Visibility & Authorization Filter
# =============================================================================
def get_visible_computers(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Admin จะมองเห็นเครื่องคอมพิวเตอร์ทั้งหมด
    User ทั่วไปจะเห็นเฉพาะเครื่องที่ว่าง หรือเครื่องที่ตนเองเป็นผู้จองไว้เท่านั้น
    """
    all_pcs = get_all_computers()
    if user.get("role") == ROLE_ADMIN:
        return all_pcs

    username = user.get("sub")
    return [
        pc for pc in all_pcs
        if pc["status"] != STATUS_BOOKED or pc.get("bookedBy") == username
    ]


# =============================================================================
# 🩺 Health Check Endpoint
# =============================================================================
@app.get("/lab/health")
@app.get("/health")
def health_check():
    """ตรวจสอบสถานะความพร้อมของระบบ (Health check)"""
    return {
        "status": "ok",
        "service": "Lab Booking Web Application (Application Layer)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }


# =============================================================================
# 🌐 Public Routes
# =============================================================================
@app.get("/lab", response_class=HTMLResponse)
@app.get("/lab/", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
async def public_home_page(
    request: Request,
    error: Optional[str] = None,
    sso_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)
):
    """หน้าแรกของระบบ (Landing Page) แสดงสถานะ Login ของผู้ใช้"""
    user = verify_token(sso_token)
    
    error_messages = {
        "auth_required": "กรุณาเข้าสู่ระบบ (Login) เพื่อรับ Token ก่อนเข้าใช้งานหน้าระบบจองแล็บ",
        "invalid_token": "บัตรผ่าน (Token) หมดอายุหรือไม่ถูกต้อง กรุณาเข้าสู่ระบบใหม่อีกครั้ง"
    }
    error_message = error_messages.get(error)

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "user": user,
            "error": error_message
        }
    )


@app.get("/logout")
@app.post("/logout")
@app.get("/lab/logout")
@app.post("/lab/logout")
def lab_logout():
    """ออกจากระบบ ลบ SSO Cookie และ Redirect กลับหน้าแรก"""
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


# =============================================================================
# 🔒 Protected Routes (ต้องผ่านการยืนยันตัวตนด้วย Token)
# =============================================================================
@app.get("/booking", response_class=HTMLResponse)
@app.get("/lab/booking", response_class=HTMLResponse)
async def protected_booking_page(
    request: Request,
    sso_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    authorization: Optional[str] = Header(default=None)
):
    """หน้า UI สำหรับการจองเครื่องแล็บ ตรวจสอบสิทธิ์ผ่าน Cookie หรือ Bearer"""
    token = extract_token_from_request(sso_token, bearer, authorization)
    user = verify_token(token)

    if not user:
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header or request.method == "GET":
            return RedirectResponse(url="/?error=auth_required", status_code=status.HTTP_302_FOUND)
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Unauthorized", "message": "Auth layer verification failed"}
        )

    computers = get_visible_computers(user)
    return templates.TemplateResponse(
        request=request,
        name="booking.html",
        context={
            "user": user,
            "computers": computers
        }
    )


# -----------------------------------------------------------------------------
# Protected APIs
# -----------------------------------------------------------------------------
@app.get("/api/me")
@app.get("/lab/api/me")
def get_current_user_profile(
    auth_data: Dict[str, Any] = Depends(get_current_user_and_token)
):
    """API สำหรับดึงข้อมูลโปรไฟล์ของผู้ใช้ปัจจุบัน"""
    return {
        "authenticated": True,
        "user": auth_data["user"]
    }


@app.get("/api/computers")
@app.get("/lab/api/computers")
def get_computers(
    auth_data: Dict[str, Any] = Depends(get_current_user_and_token)
):
    """API สำหรับดึงรายการเครื่องคอมพิวเตอร์ตามสิทธิ์ของผู้ใช้"""
    user = auth_data["user"]
    return {
        "computers": get_visible_computers(user),
        "currentUser": user.get("sub"),
        "role": user.get("role")
    }


@app.post("/api/book")
@app.post("/lab/api/book")
def book_computer(
    req: BookRequest,
    auth_data: Dict[str, Any] = Depends(get_current_user_and_token)
):
    """API สำหรับทำการจองเครื่องคอมพิวเตอร์"""
    user = auth_data["user"]
    username = user.get("sub")
    is_admin = user.get("role") == ROLE_ADMIN

    target = find_computer_by_id(req.computerId)

    # Guard Clause 1: เครื่องไม่มีอยู่ในระบบ
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ไม่พบเครื่องคอมพิวเตอร์นี้"
        )

    # Guard Clause 2: เครื่องถูกจองไปแล้วโดยผู้อื่น (ยกเว้น Admin)
    if target["status"] == STATUS_BOOKED and target["bookedBy"] != username and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"เครื่องนี้ถูกจองไปแล้วโดย {target['bookedBy']}"
        )

    # บันทึกการจอง
    selected_time = req.timeSlot or DEFAULT_TIME_SLOT
    book_computer_record(req.computerId, username, selected_time)

    return {
        "success": True,
        "message": f"จองเครื่อง {req.computerId} สำเร็จ!",
        "computers": get_visible_computers(user)
    }


@app.post("/api/cancel")
@app.post("/lab/api/cancel")
def cancel_booking(
    req: CancelRequest,
    auth_data: Dict[str, Any] = Depends(get_current_user_and_token)
):
    """
    API สำหรับยกเลิกการจองเครื่องคอมพิวเตอร์
    เฉพาะผู้ที่จอง หรือ Admin เท่านั้นที่มีสิทธิ์ยกเลิก
    """
    user = auth_data["user"]
    username = user.get("sub")
    user_role = user.get("role")
    is_admin = user_role == ROLE_ADMIN

    target = find_computer_by_id(req.computerId)

    # Guard Clause 1: ตรวจสอบว่าเครื่องมีอยู่จริง
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ไม่พบเครื่องคอมพิวเตอร์นี้"
        )

    # Guard Clause 2: ตรวจสอบสิทธิ์ (เจ้าของเครื่อง หรือ Admin)
    is_owner = target["bookedBy"] == username
    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"ไม่มีสิทธิ์ยกเลิก: เครื่องนี้ถูกจองโดย {target['bookedBy']} (สิทธิ์ของคุณคือ {user_role})"
        )

    # ทำการยกเลิกการจอง
    cancel_booking_record(req.computerId)

    return {
        "success": True,
        "message": f"ยกเลิกการจองเครื่อง {req.computerId} สำเร็จ!",
        "computers": get_visible_computers(user)
    }


# =============================================================================
# Entrypoint การรัน Service แบบ Standalone
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
