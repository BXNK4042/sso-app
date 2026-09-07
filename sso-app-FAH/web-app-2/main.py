"""
=============================================================================
Web Application 2 - IT Equipment Loan System (Port 5001)
Architecture Role: 4. Application Layer (FastAPI + Jinja2)

ปรับปรุงเพื่อความถูกต้องตามสถาปัตยกรรม (Separation of Concerns):
- ลบ Auth Proxy (/auth/login): ให้เป็นหน้าที่ของ Auth Layer (Central Auth) 100%
- ลบ Database Layer (SQLite / init_db / get_db): ให้เป็นหน้าที่ของ Database Layer (Bank)
- Application Layer จัดการเฉพาะ:
  1. Routing & Jinja2 Template Rendering (Home, Borrow)
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
PORT: int = int(os.getenv("PORT", "5001"))
JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secure-jwt-sso-secret-key-2026")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
COOKIE_NAME: str = os.getenv("COOKIE_NAME", "sso_token")

# ค่าคงที่สำหรับ Business Logic และ Security
ROLE_ADMIN: str = "Admin"
STATUS_AVAILABLE: str = "available"
STATUS_BORROWED: str = "borrowed"
DEFAULT_DUE_DATE: str = "คืนภายใน 17:00 วันนี้"

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
    title="Web Application 2 - IT Equipment Loan (Application Layer)",
    description="IT Equipment Loan System - Application Layer (FastAPI + Jinja2)",
    version="2.2.0",
    docs_url="/equipment/docs",
    openapi_url="/equipment/openapi.json",
    redoc_url="/equipment/redoc"
)

security_bearer = HTTPBearer(auto_error=False)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Mount Static Files สำหรับ CSS / Assets
if os.path.exists(PUBLIC_DIR):
    app.mount("/equipment/public", StaticFiles(directory=PUBLIC_DIR), name="equip_public")
    app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")


# =============================================================================
# [APPLICATION LAYER: In-Memory Data Store & Interface]
# แยกออกจาก Database Layer (SQLite) โดยสิ้นเชิง:
# ใช้ In-Memory Store สำหรับจำลองข้อมูลอุปกรณ์และพร้อมเชื่อมต่อกับ Database Layer
# =============================================================================
INITIAL_EQUIPMENTS = [
    {"id": "EQ-01", "name": "MacBook Pro M3 (16GB RAM)", "category": "Laptop", "status": STATUS_AVAILABLE, "borrowedBy": None, "dueDate": None},
    {"id": "EQ-02", "name": "Dell XPS 15 (Core i7 / 32GB)", "category": "Laptop", "status": STATUS_AVAILABLE, "borrowedBy": None, "dueDate": None},
    {"id": "EQ-03", "name": "iPad Pro 12.9\" + Apple Pencil", "category": "Tablet", "status": STATUS_BORROWED, "borrowedBy": "student99", "dueDate": "คืนภายใน 17:00 วันนี้"},
    {"id": "EQ-04", "name": "Multi-Port USB-C to 4K HDMI Hub", "category": "Accessory", "status": STATUS_AVAILABLE, "borrowedBy": None, "dueDate": None},
    {"id": "EQ-05", "name": "Meta Quest 3 VR Headset (512GB)", "category": "VR / AR", "status": STATUS_AVAILABLE, "borrowedBy": None, "dueDate": None},
    {"id": "EQ-06", "name": "Arduino & IoT Sensors Starter Kit", "category": "Electronics", "status": STATUS_AVAILABLE, "borrowedBy": None, "dueDate": None}
]

equipments_store: List[Dict[str, Any]] = [dict(e) for e in INITIAL_EQUIPMENTS]


def get_all_equipments() -> List[Dict[str, Any]]:
    """ดึงรายการอุปกรณ์ทั้งหมด"""
    return [dict(e) for e in equipments_store]


def find_equipment_by_id(eq_id: str) -> Optional[Dict[str, Any]]:
    """ค้นหาอุปกรณ์ตาม ID"""
    for eq in equipments_store:
        if eq["id"] == eq_id:
            return eq
    return None


def borrow_equipment_record(eq_id: str, username: str, due_date: str) -> None:
    """อัปเดตสถานะการยืมอุปกรณ์"""
    eq = find_equipment_by_id(eq_id)
    if eq:
        eq["status"] = STATUS_BORROWED
        eq["borrowedBy"] = username
        eq["dueDate"] = due_date


def return_equipment_record(eq_id: str) -> None:
    """อัปเดตสถานะการคืนอุปกรณ์"""
    eq = find_equipment_by_id(eq_id)
    if eq:
        eq["status"] = STATUS_AVAILABLE
        eq["borrowedBy"] = None
        eq["dueDate"] = None


# =============================================================================
# Pydantic Request Models
# =============================================================================
class BorrowRequest(BaseModel):
    equipmentId: str
    dueDate: Optional[str] = DEFAULT_DUE_DATE


class ReturnRequest(BaseModel):
    equipmentId: str


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
def get_visible_equipments(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Admin จะมองเห็นอุปกรณ์ทั้งหมด
    User ทั่วไปจะเห็นเฉพาะอุปกรณ์ที่ว่าง หรืออุปกรณ์ที่ตนเองเป็นผู้ยืมไว้เท่านั้น
    """
    all_items = get_all_equipments()
    if user.get("role") == ROLE_ADMIN:
        return all_items

    username = user.get("sub")
    return [
        eq for eq in all_items
        if eq["status"] != STATUS_BORROWED or eq.get("borrowedBy") == username
    ]


# =============================================================================
# 🩺 Health Check Endpoint
# =============================================================================
@app.get("/equipment/health")
@app.get("/health")
def health_check():
    """ตรวจสอบสถานะความพร้อมของระบบ (Health check)"""
    return {
        "status": "ok",
        "service": "IT Equipment Loan Web Application (Application Layer)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }


# =============================================================================
# 🌐 Public Routes
# =============================================================================
@app.get("/equipment", response_class=HTMLResponse)
@app.get("/equipment/", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
async def public_home_page(
    request: Request,
    error: Optional[str] = None,
    sso_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)
):
    """หน้าแรกของระบบ (Landing Page) แสดงสถานะ Login ของผู้ใช้"""
    user = verify_token(sso_token)
    
    error_messages = {
        "auth_required": "กรุณาเข้าสู่ระบบ (Login) เพื่อรับ Token ก่อนเข้าใช้งานหน้าระบบยืมอุปกรณ์",
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
@app.get("/equipment/logout")
@app.post("/equipment/logout")
def equip_logout():
    """ออกจากระบบ ลบ SSO Cookie และ Redirect กลับหน้าแรก"""
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


# =============================================================================
# 🔒 Protected Routes (ต้องผ่านการยืนยันตัวตนด้วย Token)
# =============================================================================
@app.get("/borrow", response_class=HTMLResponse)
@app.get("/equipment/borrow", response_class=HTMLResponse)
async def protected_borrow_page(
    request: Request,
    sso_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    authorization: Optional[str] = Header(default=None)
):
    """หน้า UI สำหรับการยืมอุปกรณ์ ตรวจสอบสิทธิ์ผ่าน Cookie หรือ Bearer"""
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

    equipments = get_visible_equipments(user)
    return templates.TemplateResponse(
        request=request,
        name="borrow.html",
        context={
            "user": user,
            "equipments": equipments
        }
    )


# -----------------------------------------------------------------------------
# Protected APIs
# -----------------------------------------------------------------------------
@app.get("/equipment/api/me")
@app.get("/api/me")
def get_current_user_profile(
    auth_data: Dict[str, Any] = Depends(get_current_user_and_token)
):
    """API สำหรับดึงข้อมูลโปรไฟล์ของผู้ใช้ปัจจุบัน"""
    return {
        "authenticated": True,
        "user": auth_data["user"]
    }


@app.get("/equipment/api/equipments")
@app.get("/api/equipments")
def get_equipments(
    auth_data: Dict[str, Any] = Depends(get_current_user_and_token)
):
    """API สำหรับดึงรายการอุปกรณ์ตามสิทธิ์ของผู้ใช้"""
    user = auth_data["user"]
    return {
        "equipments": get_visible_equipments(user),
        "currentUser": user.get("sub"),
        "role": user.get("role")
    }


@app.post("/equipment/api/borrow")
@app.post("/api/borrow")
def borrow_equipment(
    req: BorrowRequest,
    auth_data: Dict[str, Any] = Depends(get_current_user_and_token)
):
    """API สำหรับทำการยืมอุปกรณ์"""
    user = auth_data["user"]
    username = user.get("sub")
    is_admin = user.get("role") == ROLE_ADMIN

    target = find_equipment_by_id(req.equipmentId)

    # Guard Clause 1: ไม่พบอุปกรณ์ในระบบ
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ไม่พบอุปกรณ์นี้ในระบบ"
        )

    # Guard Clause 2: อุปกรณ์ถูกยืมไปแล้วโดยผู้อื่น (ยกเว้น Admin)
    if target["status"] == STATUS_BORROWED and target["borrowedBy"] != username and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"อุปกรณ์นี้ถูกยืมไปแล้วโดย {target['borrowedBy']}"
        )

    # บันทึกการยืมอุปกรณ์
    selected_due_date = req.dueDate or DEFAULT_DUE_DATE
    borrow_equipment_record(req.equipmentId, username, selected_due_date)

    return {
        "success": True,
        "message": f"ยืมอุปกรณ์ {req.equipmentId} สำเร็จ!",
        "equipments": get_visible_equipments(user)
    }


@app.post("/equipment/api/return")
@app.post("/api/return")
def return_equipment(
    req: ReturnRequest,
    auth_data: Dict[str, Any] = Depends(get_current_user_and_token)
):
    """
    API สำหรับส่งคืนอุปกรณ์
    เฉพาะผู้ที่ยืม หรือ Admin เท่านั้นที่มีสิทธิ์คืน
    """
    user = auth_data["user"]
    username = user.get("sub")
    user_role = user.get("role")
    is_admin = user_role == ROLE_ADMIN

    target = find_equipment_by_id(req.equipmentId)

    # Guard Clause 1: ตรวจสอบว่าอุปกรณ์มีอยู่จริง
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ไม่พบอุปกรณ์นี้ในระบบ"
        )

    # Guard Clause 2: ตรวจสอบสิทธิ์ (ผู้ยืม หรือ Admin)
    is_borrower = target["borrowedBy"] == username
    if not (is_borrower or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"ไม่มีสิทธิ์คืน: อุปกรณ์นี้ถูกยืมโดย {target['borrowedBy']} (สิทธิ์ของคุณคือ {user_role})"
        )

    # ทำการส่งคืนอุปกรณ์
    return_equipment_record(req.equipmentId)

    return {
        "success": True,
        "message": f"ส่งคืนอุปกรณ์ {req.equipmentId} สำเร็จ!",
        "equipments": get_visible_equipments(user)
    }


# =============================================================================
# Entrypoint การรัน Service แบบ Standalone
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
