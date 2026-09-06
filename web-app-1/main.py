"""
=============================================================================
Web Application 1 - Lab Booking System (Port 5000)
Refactored by Antigravity Agent using the 'refactor' skill:
- Code Smells Addressed:
  1. Dead Code: ลบ unused imports (base64, Response) และลบ duplicate variables (AUTH_SERVICE_URL)
  2. Magic Numbers / Strings: กำหนดค่าคงที่ (Constants) เช่น TIME_SLOT, STATUS, COOKIE_MAX_AGE
  3. DRY (Don't Repeat Yourself): รวม logic การดึง JWT Token ไว้ใน helper function เดียว
  4. Single Responsibility & Clean Database Layer: แยกฟังก์ชันจัดการ SQL เป็น helper functions ชัดเจน
  5. Nested Conditionals -> Guard Clauses: ใช้ Early Return ตรวจสอบสิทธิ์ (Authorization) ให้อ่านง่าย
  6. Defensive Directory Fallback: รองรับทั้งกรณีมีโฟลเดอร์ views/public หรือไฟล์อยู่ที่ root จาก zip
=============================================================================
"""

import os
import time
import json
import sqlite3
import urllib.request
import urllib.error
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
# [REFACTOR: Magic Numbers & Strings to Constants]
# ย้ายค่า Hardcoded และ Magic strings ต่างๆ มาเป็นค่าคงที่เพื่อง่ายต่อการแก้ไขและอ่านโค้ด
# =============================================================================
PORT: int = int(os.getenv("PORT", "5000"))
JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secure-jwt-sso-secret-key-2026")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
COOKIE_NAME: str = os.getenv("COOKIE_NAME", "sso_token")
AUTH_SERVICE_URL: str = os.getenv("AUTH_SERVICE_URL", "http://central-auth:4000/auth/login")

# ค่าคงที่สำหรับ Business Logic และ Security
ROLE_ADMIN: str = "Admin"
STATUS_AVAILABLE: str = "available"
STATUS_BOOKED: str = "booked"
DEFAULT_TIME_SLOT: str = "13:00 - 16:00"
COOKIE_MAX_AGE_SECONDS: int = 7200  # 2 ชั่วโมง

# =============================================================================
# [REFACTOR: Defensive Directory Resolution]
# ตรวจสอบ path ของ views และ public ให้ยืดหยุ่น:
# หากแตก zip มาแล้วไฟล์ html/css อยู่ที่ root directory จะไม่เกิด Error TemplateNotFound
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIEWS_SUBDIR = os.path.join(BASE_DIR, "views")
PUBLIC_SUBDIR = os.path.join(BASE_DIR, "public")

TEMPLATES_DIR = VIEWS_SUBDIR if os.path.exists(VIEWS_SUBDIR) else BASE_DIR
PUBLIC_DIR = PUBLIC_SUBDIR if os.path.exists(PUBLIC_SUBDIR) else BASE_DIR
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "lab.db"))

# =============================================================================
# FastAPI Application & Middleware Initialization
# =============================================================================
app = FastAPI(
    title="Web Application 1 - Lab Booking",
    description="Lab Booking System with Public Home Page and Protected Booking Page (Refactored)",
    version="2.1.0",
    docs_url="/lab/docs",
    openapi_url="/lab/openapi.json",
    redoc_url="/lab/redoc"
)

security_bearer = HTTPBearer(auto_error=False)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Mount Static Files สำหรับ CSS / JS / Assets
if os.path.exists(PUBLIC_DIR):
    app.mount("/lab/public", StaticFiles(directory=PUBLIC_DIR), name="lab_public")
    app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")


# =============================================================================
# [REFACTOR: Database Layer]
# แยกการเข้าถึงฐานข้อมูล SQLite ให้ชัดเจน มี Transaction ปลอดภัย และคืนค่าข้อมูลแบบ Type-safe
# =============================================================================
def get_db() -> sqlite3.Connection:
    """สร้างและคืน connection ไปยัง SQLite Database พร้อม row_factory เพื่อให้อ่าน field เป็น dict ได้"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """สร้างตารางและ Seed ข้อมูลเริ่มต้นหากยังไม่มีข้อมูลในตาราง lab_computers"""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lab_computers (
                id TEXT PRIMARY KEY,
                room TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'available',
                booked_by TEXT,
                time TEXT
            )
        """)
        cursor = conn.execute("SELECT COUNT(*) FROM lab_computers")
        if cursor.fetchone()[0] == 0:
            seed_data = [
                ("PC-01", "Lab 401 (Networking)", STATUS_AVAILABLE, None, None),
                ("PC-02", "Lab 401 (Networking)", STATUS_AVAILABLE, None, None),
                ("PC-03", "Lab 401 (Networking)", STATUS_BOOKED, "student99", "09:00 - 12:00"),
                ("PC-04", "Lab 402 (Cybersecurity)", STATUS_AVAILABLE, None, None),
                ("PC-05", "Lab 402 (Cybersecurity)", STATUS_AVAILABLE, None, None),
                ("PC-06", "Lab 402 (Cybersecurity)", STATUS_AVAILABLE, None, None)
            ]
            conn.executemany(
                "INSERT INTO lab_computers (id, room, status, booked_by, time) VALUES (?, ?, ?, ?, ?)",
                seed_data
            )
            conn.commit()

# เรียก Initialize ฐานข้อมูลตอนเริ่มทำงาน
init_db()


def db_get_all_computers() -> List[Dict[str, Any]]:
    """ดึงข้อมูลเครื่องคอมพิวเตอร์ทั้งหมดในระบบ"""
    with get_db() as conn:
        cursor = conn.execute("SELECT id, room, status, booked_by as bookedBy, time FROM lab_computers ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]


def db_find_computer_by_id(pc_id: str) -> Optional[sqlite3.Row]:
    """ค้นหาเครื่องคอมพิวเตอร์ตาม ID"""
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM lab_computers WHERE id = ?", (pc_id,))
        return cursor.fetchone()


def db_book_computer(pc_id: str, username: str, time_slot: str) -> None:
    """อัปเดตสถานะการจองเครื่องคอมพิวเตอร์ในฐานข้อมูล"""
    with get_db() as conn:
        conn.execute(
            "UPDATE lab_computers SET status = ?, booked_by = ?, time = ? WHERE id = ?",
            (STATUS_BOOKED, username, time_slot, pc_id)
        )
        conn.commit()


def db_cancel_booking(pc_id: str) -> None:
    """ยกเลิกการจองและคืนสถานะเครื่องให้ว่าง"""
    with get_db() as conn:
        conn.execute(
            "UPDATE lab_computers SET status = ?, booked_by = NULL, time = NULL WHERE id = ?",
            (STATUS_AVAILABLE, pc_id)
        )
        conn.commit()


# =============================================================================
# [REFACTOR: Pydantic Request Models]
# รองรับ Data Validation ป้องกัน Input ที่ไม่พึงประสงค์
# =============================================================================
class BookRequest(BaseModel):
    computerId: str
    timeSlot: Optional[str] = DEFAULT_TIME_SLOT


class CancelRequest(BaseModel):
    computerId: str


# =============================================================================
# [REFACTOR: DRY Authentication & Token Utilities]
# รวม Logic การแกะ Token และตรวจสอบสิทธิ์ไว้จุดเดียว ไม่เขียนซ้ำซ้อน
# =============================================================================
def verify_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """ถอดรหัสและตรวจสอบความถูกต้องของ JWT Token"""
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
    """
    [REFACTOR: DRY Helper]
    ดึง Token จาก Bearer Credentials, Authorization Header, หรือ SSO Cookie ตามลำดับความสำคัญ
    """
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
    """
    FastAPI Dependency สำหรับ Endpoint ที่ต้องการการยืนยันตัวตน (Protected Endpoints)
    ใช้ Guard Clauses ตัดจบ error ตั้งแต่เนิ่นๆ หากไม่มี token หรือ token ไม่ถูกต้อง
    """
    token = extract_token_from_request(sso_token, bearer, authorization)
    
    # Guard Clause 1: ตรวจสอบว่ามี Token ส่งมาหรือไม่
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token or SSO cookie."
        )

    # Guard Clause 2: ตรวจสอบความถูกต้องและอายุของ Token
    user = verify_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token"
        )

    return {"user": user, "token": token}


# =============================================================================
# [REFACTOR: Business Logic - Visibility & Authorization Filter]
# แยก Logic การกรองรายการเครื่องที่ User มีสิทธิ์เห็นออกมาเป็น Pure Function
# =============================================================================
def get_visible_computers(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Admin จะมองเห็นเครื่องคอมพิวเตอร์ทั้งหมด
    User ทั่วไปจะเห็นเฉพาะเครื่องที่ 'ว่าง' หรือเครื่องที่ตนเองเป็นผู้จองไว้เท่านั้น
    """
    all_pcs = db_get_all_computers()
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
        "service": "Lab Booking Web Application (Refactored)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }


# =============================================================================
# 🌐 Public Routes (ไม่ต้องใช้ Token)
# =============================================================================
@app.post("/auth/login")
async def proxy_auth_login(request: Request):
    """
    ส่งต่อคำขอ Login ไปยัง Central Auth Service และบันทึก SSO Cookie เมื่อสำเร็จ
    """
    body = await request.json()
    try:
        req = urllib.request.Request(
            AUTH_SERVICE_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            token = res_data.get("access_token") or res_data.get("token")
            resp = JSONResponse(content=res_data)
            if token:
                resp.set_cookie(
                    key=COOKIE_NAME,
                    value=token,
                    path="/",
                    httponly=True,
                    samesite="lax",
                    max_age=COOKIE_MAX_AGE_SECONDS
                )
            return resp

    except urllib.error.HTTPError as e:
        error_body = {}
        try:
            error_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            pass
        raise HTTPException(
            status_code=e.code,
            detail=error_body.get("detail", error_body.get("message", "Authentication failed"))
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot connect to Auth Layer: {str(e)}")


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
    
    # แมป error code เป็นข้อความภาษาไทยที่สื่อความหมายชัดเจน
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
    """
    [REFACTOR: Clean Token Extraction & Guard Clauses]
    หน้า UI สำหรับการจองเครื่องแล็บ ตรวจสอบสิทธิ์ผ่าน Cookie หรือ Bearer
    """
    token = extract_token_from_request(sso_token, bearer, authorization)
    user = verify_token(token)

    # Guard Clause: หากยังไม่ได้ยืนยันตัวตน ให้ Redirect หรือตอบ 401
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
    """
    [REFACTOR: Guard Clauses for Booking Logic]
    API สำหรับทำการจองเครื่องคอมพิวเตอร์
    """
    user = auth_data["user"]
    username = user.get("sub")
    is_admin = user.get("role") == ROLE_ADMIN

    target = db_find_computer_by_id(req.computerId)

    # Guard Clause 1: เครื่องไม่มีอยู่ในระบบ
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ไม่พบเครื่องคอมพิวเตอร์นี้"
        )

    # Guard Clause 2: เครื่องถูกจองไปแล้วโดยผู้อื่น (ยกเว้น Admin)
    if target["status"] == STATUS_BOOKED and target["booked_by"] != username and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"เครื่องนี้ถูกจองไปแล้วโดย {target['booked_by']}"
        )

    # บันทึกการจองลงฐานข้อมูล
    selected_time = req.timeSlot or DEFAULT_TIME_SLOT
    db_book_computer(req.computerId, username, selected_time)

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
    [REFACTOR: Clean Authorization Check & Guard Clauses]
    API สำหรับยกเลิกการจองเครื่องคอมพิวเตอร์
    เฉพาะผู้ที่จอง หรือ Admin เท่านั้นที่มีสิทธิ์ยกเลิก
    """
    user = auth_data["user"]
    username = user.get("sub")
    user_role = user.get("role")
    is_admin = user_role == ROLE_ADMIN

    target = db_find_computer_by_id(req.computerId)

    # Guard Clause 1: ตรวจสอบว่าเครื่องมีอยู่จริง
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ไม่พบเครื่องคอมพิวเตอร์นี้"
        )

    # Guard Clause 2: ตรวจสอบสิทธิ์ (เจ้าของเครื่อง หรือ Admin)
    is_owner = target["booked_by"] == username
    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"ไม่มีสิทธิ์ยกเลิก: เครื่องนี้ถูกจองโดย {target['booked_by']} (สิทธิ์ของคุณคือ {user_role})"
        )

    # ทำการยกเลิกการจองในฐานข้อมูล
    db_cancel_booking(req.computerId)

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
