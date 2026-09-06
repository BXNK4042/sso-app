# ==============================================================================
# นำเข้าโมดูลและไลบรารีมาตรฐานที่จำเป็นสำหรับการทำงาน
# ==============================================================================
import os                                      # โมดูลสำหรับเข้าถึงสภาพแวดล้อมระบบปฏิบัติการและอ่าน Environment Variables
from datetime import datetime, timedelta       # คลาสสำหรับจัดการวันและเวลา คำนวณอายุการใช้งานของ Token

# ==============================================================================
# นำเข้าไลบรารีภายนอกสำหรับการจัดการความปลอดภัยและโปรโตคอลเครือข่าย
# ==============================================================================
import jwt                                     # ไลบรารี PyJWT สำหรับการเข้ารหัส (Encode) และลงลายเซ็นดิจิทัลให้กับ JSON Web Token
from pyrad.client import Client                # คลาสสร้าง RADIUS Client เพื่อส่งแพ็กเก็ตไปยัง FreeRADIUS Server
from pyrad.dictionary import Dictionary        # คลาสโหลดพจนานุกรมคำศัพท์ Attribute สำหรับสร้างแพ็กเก็ต RADIUS
import pyrad.packet                            # โมดูลบรรจุโครงสร้างและรหัสสถานะแพ็กเก็ต RADIUS เช่น AccessRequest, AccessAccept

# ==============================================================================
# นำเข้าเครื่องมือจากเฟรมเวิร์ก FastAPI สำหรับสร้างเว็บเซิร์ฟเวอร์
# ==============================================================================
from fastapi import FastAPI, Request, Form, status     # ส่วนประกอบหลักของ FastAPI: แอปรองรับ Request, ข้อมูลแบบ Form และ HTTP Status Code
from fastapi.responses import HTMLResponse, RedirectResponse  # อ็อบเจกต์สำหรับส่งหน้าเว็บ HTML และคำสั่ง Redirect ไปยัง URL อื่น

# ------------------------------------------------------------------------------
# 1. กำหนดค่าเริ่มต้นของระบบ (Configuration & Environment Variables)
# ------------------------------------------------------------------------------
# สร้างอินสแตนซ์หลักของแอปพลิเคชัน FastAPI พร้อมตั้งชื่อระบบ
app = FastAPI(title="Central Authentication Service")

# พอร์ตสำหรับรันเซิร์ฟเวอร์ Central Auth (ค่าเริ่มต้นคือ 3000)
PORT = int(os.getenv("PORT", 3000))

# ที่อยู่โฮสต์ของ FreeRADIUS (ค่าเริ่มต้นอ้างอิงชื่อ Container 'freeradius' ใน Docker Network)
RADIUS_HOST = os.getenv("RADIUS_HOST", "freeradius")

# พอร์ต UDP สำหรับตรวจสอบสิทธิ์ผู้ใช้ของ FreeRADIUS (มาตรฐานคือ 1812)
RADIUS_PORT = int(os.getenv("RADIUS_PORT", 1812))

# กุญแจลับ (Shared Secret) ที่ต้องตรงกันระหว่าง RADIUS Client และ FreeRADIUS Server
RADIUS_SECRET = os.getenv("RADIUS_SECRET", "testing123")

# กุญแจลับสำหรับเซ็นลายเซ็นดิจิทัลบน JWT Token เพื่อไม่ให้แอปพลิเคชันอื่นปลอมแปลงได้
JWT_SECRET = os.getenv("JWT_SECRET", "kmitl_chumphon_sso_secret_key_2026")

# อัลกอริทึมเข้ารหัสสำหรับสร้างลายเซ็นดิจิทัล (HMAC-SHA256)
JWT_ALGORITHM = "HS256"

# ชื่อของ Cookie ที่จะใช้จัดเก็บ JWT Token บนเบราว์เซอร์ของผู้ใช้งาน
COOKIE_NAME = "sso_auth_token"


# ------------------------------------------------------------------------------
# 2. ฟังก์ชันตรวจสอบสิทธิ์ผู้ใช้งานกับ FreeRADIUS (RADIUS Authentication)
# ------------------------------------------------------------------------------
def authenticate_with_radius(username: str, password: str) -> bool:
    """ส่งข้อมูลชื่อผู้ใช้และรหัสผ่านไปยืนยันกับ FreeRADIUS Server ผ่านโปรโตคอล UDP พอร์ต 1812"""
    try:
        # สร้าง Client จำลองการเป็นเครื่องตรวจสอบสิทธิ์ กำหนด Host, Port, Secret และไฟล์พจนานุกรม
        srv = Client(
            server=RADIUS_HOST,
            authport=RADIUS_PORT,
            secret=RADIUS_SECRET.encode(),
            dict=Dictionary("dictionary")
        )

        # ตั้งค่า Socket Timeout ไว้ที่ 3 วินาที เพื่อป้องกันระบบค้างตลอดกาลหาก UDP แพ็กเก็ตสูญหาย
        srv.timeout = 3

        # สร้างแพ็กเก็ตขอสิทธิ์ประเภท Access-Request พร้อมระบุชื่อผู้ใช้งาน
        req = srv.CreateAuthPacket(code=pyrad.packet.AccessRequest, User_Name=username)

        # นำรหัสผ่านไปเข้ารหัสตามมาตรฐาน RADIUS Password Hashing ก่อนบรรจุลงแพ็กเก็ต
        req["User-Password"] = req.PwCrypt(password)

        # ส่งแพ็กเก็ต UDP ออกไป และรอรับการตอบกลับจาก FreeRADIUS Server
        reply = srv.SendPacket(req)

        # ส่งคืนค่า True หาก RADIUS ตอบกลับเป็น AccessAccept (1)
        return reply.code == pyrad.packet.AccessAccept

    except Exception as e:
        # ดักจับข้อผิดพลาดทั้งหมด เช่น Network Unreachable หรือ Timeout แล้วพิมพ์ Log แจ้งเตือน
        print(f"[RADIUS ERROR] เกิดข้อผิดพลาดในการเชื่อมต่อ RADIUS: {e}")
        # ส่งคืนค่า False เพื่อปฏิเสธการเข้าสู่ระบบกรณีเกิดความขัดข้องทางเทคนิค
        return False


# ------------------------------------------------------------------------------
# 3. จุดแสดงหน้าฟอร์มเข้าสู่ระบบ (Centralized Login UI)
# ------------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
@app.get("/auth/login", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request, redirect: str = "/lab/", error: str = None):
    """เรนเดอร์หน้าตาฟอร์มเข้าสู่ระบบ รองรับทั้งการต่อตรงและผ่าน Nginx Reverse Proxy"""
    # ตรวจสอบว่ามีการส่งพารามิเตอร์ error มาหรือไม่เพื่อแสดงกล่องแจ้งเตือนสีแดง
    error_banner = ""
    if error:
        error_banner = """
        <div class="alert-box">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span>ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง</span>
        </div>
        """

    # รหัสโครงสร้างหน้าเว็บ HTML พร้อมตกแต่งด้วยสไตล์ CSS สมัยใหม่
    html_content = f"""
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Central Authentication Service (SSO)</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&display=swap');

            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
                font-family: 'Sarabun', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            body {{
                background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                padding: 20px;
            }}
            .card {{
                background: #FFFFFF;
                width: 100%;
                max-width: 420px;
                border-radius: 16px;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.4);
                overflow: hidden;
            }}
            .card-header {{
                background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%);
                color: #FFFFFF;
                text-align: center;
                padding: 35px 24px 25px;
            }}
            .card-header h1 {{
                font-size: 22px;
                font-weight: 700;
                margin-bottom: 6px;
                letter-spacing: -0.5px;
            }}
            .card-header p {{
                font-size: 13px;
                opacity: 0.9;
                font-weight: 300;
            }}
            .card-body {{
                padding: 30px 25px;
            }}
            .alert-box {{
                background-color: #FEE2E2;
                border: 1px solid #F87171;
                color: #B91C1C;
                padding: 12px 14px;
                border-radius: 8px;
                font-size: 13.5px;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .form-group {{
                margin-bottom: 20px;
            }}
            .form-group label {{
                display: block;
                font-size: 13.5px;
                font-weight: 600;
                color: #334155;
                margin-bottom: 8px;
            }}
            .form-group input {{
                width: 100%;
                padding: 12px 14px;
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                font-size: 14.5px;
                color: #0F172A;
                outline: none;
                transition: all 0.2s ease-in-out;
            }}
            .form-group input:focus {{
                border-color: #0284C7;
                box-shadow: 0 0 0 3.5px rgba(2, 132, 199, 0.15);
            }}
            .btn-submit {{
                width: 100%;
                padding: 13px;
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                box-shadow: 0 4px 6px -1px rgba(2, 132, 199, 0.2);
            }}
            .btn-submit:hover {{
                background-color: #0369A1;
                box-shadow: 0 6px 8px -1px rgba(2, 132, 199, 0.3);
            }}
            .card-footer {{
                text-align: center;
                padding: 16px 20px;
                font-size: 12px;
                color: #64748b;
                border-top: 1px solid #F1F5F9;
                background-color: #F8FAFC;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="card-header">
                <h1>ระบบยืนยันตัวตนกลาง (SSO)</h1>
                <p>Central Authentication Service & FreeRADIUS</p>
            </div>
            <div class="card-body">
                {error_banner}
                <!-- กำหนด action เป็น Relative Path 'login' เพื่อรองรับทั้ง /login และ /auth/login -->
                <form action="login" method="POST">
                    <!-- ซ่อนพารามิเตอร์ปลายทางไว้ในฟอร์มเพื่อใช้ส่งผู้ใช้กลับไปยังหน้าเดิม -->
                    <input type="hidden" name="redirect_url" value="{redirect}">

                    <div class="form-group">
                        <label for="username">บัญชีผู้ใช้งาน / รหัสนักศึกษา</label>
                        <input type="text" id="username" name="username" placeholder="เช่น student66000001" required autofocus>
                    </div>

                    <div class="form-group">
                        <label for="password">รหัสผ่าน</label>
                        <input type="password" id="password" name="password" placeholder="กรอกรหัสผ่านของคุณ" required>
                    </div>

                    <button type="submit" class="btn-submit">ลงชื่อเข้าใช้งาน (Sign In)</button>
                </form>
            </div>
            <div class="card-footer">
                ความปลอดภัยสูง | บันทึกรหัสผ่านผ่าน FreeRADIUS Engine
            </div>
        </div>
    </body>
    </html>
    """
    # ส่งหน้าเว็บ HTML ที่เรนเดอร์เสร็จสมบูรณ์กลับไปยังเบราว์เซอร์
    return HTMLResponse(content=html_content)


# ------------------------------------------------------------------------------
# 4. จุดรับข้อมูลการเข้าสู่ระบบ (Authentication & Token Issuing)
# ------------------------------------------------------------------------------
@app.post("/login")
@app.post("/auth/login")
async def login_handler(
    username: str = Form(...),              # รับค่าชื่อผู้ใช้จากแบบฟอร์ม
    password: str = Form(...),              # รับค่ารหัสผ่านจากแบบฟอร์ม
    redirect_url: str = Form("/lab/")       # รับค่า URL ปลายทาง (ค่าเริ่มต้นคือ /lab/)
):
    """รับข้อมูลล็อกอิน ตรวจสอบกับ RADIUS และออกบัตรผ่าน JWT Token บรรจุลง Cookie"""
    # ตรวจสอบสิทธิ์ผู้ใช้ด้วยการส่งไปเช็คกับ FreeRADIUS Server
    if not authenticate_with_radius(username, password):
        # หากรหัสผ่านผิด ให้ดีดกลับไปหน้าฟอร์มเดิมพร้อมพารามิเตอร์แจ้งเตือน error
        return RedirectResponse(
            url=f"login?redirect={redirect_url}&error=1",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # กำหนดสิทธิ์การใช้งาน (จำแนกเบื้องต้นจากชื่อผู้ใช้)
    user_role = "admin" if ("admin" in username.lower() or "teacher" in username.lower()) else "student"

    # จัดเตรียมชุดข้อมูลที่จะฝังลงในบัตรผ่านดิจิทัล (JWT Payload)
    payload = {
        "sub": username,                                   # ชื่อผู้ใช้งานหรือรหัสนักศึกษา (Subject Identifier)
        "name": username,                                  # ชื่อสำหรับแสดงผลบนแอปพลิเคชัน
        "role": user_role,                                 # บทบาทหรือสิทธิ์การเข้าถึงของผู้ใช้งาน
        "exp": datetime.utcnow() + timedelta(hours=2)      # กำหนดระยะเวลาหมดอายุของบัตร (2 ชั่วโมงนับจากเวลาปัจจุบัน)
    }

    # ผลิตและลงลายเซ็นกำกับบน Token ด้วยอัลกอริทึม HS256 และ JWT_SECRET
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # สร้างคำสั่ง HTTP 303 Redirect เพื่อส่งผู้ใช้กลับไปยังแอปพลิเคชันปลายทาง
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    # ฝัง JWT Token ลงในคุกกี้ตามมาตรฐานความปลอดภัยสูง
    response.set_cookie(
        key=COOKIE_NAME,           # ชื่อคุกกี้ 'sso_auth_token'
        value=token,               # ตัวข้อความ Token ดิจิทัล
        httponly=True,             # ป้องกันไม่ให้ JavaScript ขโมยข้อมูล (ป้องกันการโจมตี XSS)
        path="/",                  # อนุญาตให้ใช้งานคุกกี้นี้ได้ในทุก Path ของระบบเครือข่าย
        samesite="lax"             # ป้องกันการยิงคำขอข้ามไซต์ (CSRF Protection) ในระดับมาตรฐาน
    )

    # ส่งคำสั่ง Redirect พร้อมแนบคุกกี้กลับไปยังผู้ใช้งาน
    return response


# ------------------------------------------------------------------------------
# 5. จุดออกจากระบบส่วนกลาง (Central Logout)
# ------------------------------------------------------------------------------
@app.get("/logout")
@app.get("/auth/logout")
async def logout():
    """ลบคุกกี้บัตรผ่านทิ้งและดีดผู้ใช้กลับไปยังหน้าล็อกอินกลาง"""
    # สั่งให้เบราว์เซอร์ดีดกลับไปยังหน้าเข้าสู่ระบบกลาง
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    # ล้างคุกกี้ sso_auth_token ทิ้งออกจากเครื่องของผู้ใช้งาน
    response.delete_cookie(key=COOKIE_NAME, path="/")

    # ส่งผลลัพธ์กลับไปยังผู้ใช้งาน
    return response


# ------------------------------------------------------------------------------
# จุดเริ่มต้นการประมวลผลโปรแกรม (Application Entry Point)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn                                          # นำเข้าเว็บเซิร์ฟเวอร์ความเร็วสูง Uvicorn สำหรับรัน FastAPI
    # เริ่มต้นการทำงานของเซิร์ฟเวอร์ เปิดรับการเชื่อมต่อจากทุกไอพี (0.0.0.0) ตามพอร์ตที่ตั้งค่าไว้
    uvicorn.run(app, host="0.0.0.0", port=PORT)
