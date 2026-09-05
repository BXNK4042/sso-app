from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Central SSO Auth Server")

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head><title>Central SSO Auth Service</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 50px;">
            <h2>Central SSO Auth Service</h2>
            <p style="color: green; font-weight: bold;">Status: Ready & Standing By</p>
        </body>
    </html>
    """

@app.get("/verify")
def verify_token(token: str = ""):
    return {"valid": True, "user": "admin"}