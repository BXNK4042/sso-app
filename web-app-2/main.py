"""
=============================================================================
Web Application 2 - IT Equipment Loan System (Port 5001)
Refactored by Antigravity Agent using the 'refactor' skill:
- Code Smells Addressed:
  1. Dead Code: ลบ unused imports และ duplicate variables (AUTH_SERVICE_URL ถูกประกาศซ้ำ 2 ครั้ง)
  2. Magic Numbers & Strings: กำหนดค่าคงที่ (Constants) เช่น DEFAULT_DUE_DATE, STATUS, ROLE_ADMIN, COOKIE_MAX_AGE
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
PORT: int = int(os.getenv("PORT", "5001"))
JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secure-jwt-sso-secret-key-2026")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
COOKIE_NAME: str = os.getenv("COOKIE_NAME", "sso_token")
AUTH_SERVICE_URL: str = os.getenv("AUTH_SERVICE_URL", "http://central-auth:4000/auth/login")

# ค่าคงที่สำหรับ Business Logic และ Security
ROLE_ADMIN: str = "Admin"
STATUS_AVAILABLE: str = "available"
STATUS_BORROWED: str = "borrowed"
DEFAULT_DUE_DATE: str = "คืนภายใน 17:00 วันนี้"
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
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "equipment.db"))

# =============================================================================
# FastAPI Application & Middleware Initialization
# =============================================================================
app = FastAPI(
    title="Web Application 2 - IT Equipment Loan",
    description="IT Equipment Loan & Resource Management System (Refactored)",
    version="2.1.0",
    docs_url="/equipment/docs",
    openapi_url="/equipment/openapi.json",
    redoc_url="/equipment/redoc"
)

security_bearer = HTTPBearer(auto_error=False)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Mount Static Files สำหรับ CSS / JS / Assets
if os.path.exists(PUBLIC_DIR):
    app.mount("/equipment/public", StaticFiles(directory=PUBLIC_DIR), name="equip_public")
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
    """สร้างตารางและ Seed ข้อมูลเริ่มต้นหากยังไม่มีข้อมูลในตาราง equipments"""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS equipments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'available',
                borrowed_by TEXT,
                due_date TEXT
            )
        """)
        cursor = conn.execute("SELECT COUNT(*) FROM equipments")
        if cursor.fetchone()[0] == 0:
            seed_data = [
                ("EQ-01", "MacBook Pro M3 (16GB RAM)", "Laptop", STATUS_AVAILABLE, None, None),
                ("EQ-02", "Dell XPS 15 (Core i7 / 32GB)", "Laptop", STATUS_AVAILABLE, None, None),
                ("EQ-03", "iPad Pro 12.9\" + Apple Pencil", "Tablet", STATUS_BORROWED, "student99", "คืนภายใน 17:00 วันนี้"),
                ("EQ-04", "Multi-Port USB-C to 4K HDMI Hub", "Accessory", STATUS_AVAILABLE, None, None),
                ("EQ-05", "Meta Quest 3 VR Headset (512GB)", "VR / AR", STATUS_AVAILABLE, None, None),
                ("EQ-06", "Arduino & IoT Sensors Starter Kit", "Electronics", STATUS_AVAILABLE, None, None)
            ]
            conn.executemany(
                "INSERT INTO equipments (id, name, category, status, borrowed_by, due_date) VALUES (?, ?, ?, ?, ?, ?)",
                seed_data
            )
            conn.commit()

# เรียก Initialize ฐานข้อมูลตอนเริ่มทำงาน
init_db()


def db_get_all_equipments() -> List[Dict[str, Any]]:
    """ดึงข้อมูลอุปกรณ์ทั้งหมดในระบบ"""
    with get_db() as conn:
        cursor = conn.execute("SELECT id, name, category, status, borrowed_by, due_date FROM equipments ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]


def db_find_equipment_by_id(eq_id: str) -> Optional[sqlite3.Row]:
    """ค้นหาอุปกรณ์ตาม ID"""
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM equipments WHERE id = ?", (eq_id,))
        return cursor.fetchone()


def db_borrow_equipment(eq_id: str, username: str, due_date: str) -> None:
    """อัปเดตสถานะการยืมอุปกรณ์ในฐานข้อมูล"""
    with get_db() as conn:
        conn.execute(
            "UPDATE equipments SET status = ?, borrowed_by = ?, due_date = ? WHERE id = ?",
            (STATUS_BORROWED, username, due_date, eq_id)
        )
        conn.commit()


def db_return_equipment(eq_id: str) -> None:
    """อัปเดตสถานะการคืนอุปกรณ์ในฐานข้อมูล"""
    with get_db() as conn:
        conn.execute(
            "UPDATE equipments SET status = ?, borrowed_by = NULL, due_date = NULL WHERE id = ?",
            (STATUS_AVAILABLE, eq_id)
        )
        conn.commit()


# =============================================================================
# [REFACTOR: Pydantic Request Models]
# รองรับ Data Validation ป้องกัน Input ที่ไม่พึงประสงค์
# =============================================================================
class BorrowRequest(BaseModel):
    equipmentId: str
    dueDate: Optional[str] = DEFAULT_DUE_DATE


class ReturnRequest(BaseModel):
    equipmentId: str


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
# แยก Logic การกรองรายการอุปกรณ์ที่ User มีสิทธิ์เห็นออกมาเป็น Pure Function
# =============================================================================
def get_visible_equipments(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Admin จะมองเห็นอุปกรณ์ทั้งหมด
    User ทั่วไปจะเห็นเฉพาะอุปกรณ์ที่ 'ว่าง' หรืออุปกรณ์ที่ตนเองเป็นผู้ยืมไว้เท่านั้น
    """
    all_items = db_get_all_equipments()
    if user.get("role") == ROLE_ADMIN:
        return all_items

    username = user.get("sub")
    return [
        eq for eq in all_items
        if eq["status"] != STATUS_BORROWED or eq.get("borrowed_by") == username
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
        "service": "IT Equipment Loan Web Application (Refactored)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }


# =============================================================================
# 🌐 Public Routes (ไม่ต้องใช้ Token)
# =============================================================================
@app.post("/auth/login")
@app.post("/equipment/auth/login")
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

    # แมป error code เป็นข้อความภาษาไทยที่สื่อความหมายชัดเจน
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


@app.get("/equipment/logout")
@app.post("/equipment/logout")
@app.get("/logout")
@app.post("/logout")
def equip_logout():
    """ออกจากระบบ ลบ SSO Cookie และ Redirect กลับหน้าแรก"""
    response = RedirectResponse(url="/equipment/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


# =============================================================================
# 🔒 Protected Routes (ต้องผ่านการยืนยันตัวตนด้วย Token)
# =============================================================================
@app.get("/equipment/borrow", response_class=HTMLResponse)
@app.get("/borrow", response_class=HTMLResponse)
async def protected_borrow_page(
    request: Request,
    sso_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    authorization: Optional[str] = Header(default=None)
):
    """
    [REFACTOR: Clean Token Extraction & Guard Clauses]
    หน้า UI สำหรับการยืมอุปกรณ์ ตรวจสอบสิทธิ์ผ่าน Cookie หรือ Bearer
    """
    token = extract_token_from_request(sso_token, bearer, authorization)
    user = verify_token(token)

    # Guard Clause: หากยังไม่ได้ยืนยันตัวตน ให้ Redirect หรือตอบ 401
    if not user:
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header or request.method == "GET":
            return RedirectResponse(url="/equipment/?error=auth_required", status_code=status.HTTP_302_FOUND)
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
@app.get("/equipment/api/items")
@app.get("/api/items")
def get_items(
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
    """
    [REFACTOR: Guard Clauses for Borrowing Logic]
    API สำหรับทำการยืมอุปกรณ์
    """
    user = auth_data["user"]
    username = user.get("sub")
    is_admin = user.get("role") == ROLE_ADMIN

    target = db_find_equipment_by_id(req.equipmentId)

    # Guard Clause 1: ไม่พบอุปกรณ์ในระบบ
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ไม่พบอุปกรณ์นี้ในระบบ"
        )

    # Guard Clause 2: อุปกรณ์ถูกยืมไปแล้วโดยผู้อื่น (ยกเว้น Admin)
    if target["status"] == STATUS_BORROWED and target["borrowed_by"] != username and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"อุปกรณ์นี้ถูกยืมไปแล้วโดย {target['borrowed_by']}"
        )

    # บันทึกการยืมอุปกรณ์ลงฐานข้อมูล
    selected_due_date = req.dueDate or DEFAULT_DUE_DATE
    db_borrow_equipment(req.equipmentId, username, selected_due_date)

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
    [REFACTOR: Clean Authorization Check & Guard Clauses]
    API สำหรับส่งคืนอุปกรณ์
    เฉพาะผู้ที่ยืม หรือ Admin เท่านั้นที่มีสิทธิ์คืน
    """
    user = auth_data["user"]
    username = user.get("sub")
    user_role = user.get("role")
    is_admin = user_role == ROLE_ADMIN

    target = db_find_equipment_by_id(req.equipmentId)

    # Guard Clause 1: ตรวจสอบว่าอุปกรณ์มีอยู่จริง
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ไม่พบอุปกรณ์นี้ในระบบ"
        )

    # Guard Clause 2: ตรวจสอบสิทธิ์ (ผู้ยืม หรือ Admin)
    is_borrower = target["borrowed_by"] == username
    if not (is_borrower or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"ไม่มีสิทธิ์คืน: อุปกรณ์นี้ถูกยืมโดย {target['borrowed_by']} (สิทธิ์ของคุณคือ {user_role})"
        )

    # ทำการส่งคืนอุปกรณ์ในฐานข้อมูล
    db_return_equipment(req.equipmentId)

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
