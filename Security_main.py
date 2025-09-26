# backend/security_agent/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from .security_agent import SecurityAgent

app = FastAPI(title="Security Agent", version="0.1.0")

sec = SecurityAgent()


class PrecheckRequest(BaseModel):
    username: str
    password: str
    message: str


class PostcheckRequest(BaseModel):
    text: str


class PostcheckResponse(BaseModel):
    masked: str
    encrypted: str  # base64 string from Fernet


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/precheck")
def precheck(body: PrecheckRequest):
    # 1) Auth
    if not sec.authenticate_user(body.username, body.password):
        return {"ok": False, "message": "Authentication failed."}

    # 2) Block list
    if not sec.validate_input(body.message):
        return {"ok": False, "message": "Input rejected by security policy."}

    # 3) Responsible AI
    ok, msg = sec.responsible_ai_filter(body.message)
    if not ok:
        return {"ok": False, "message": msg}

    return {"ok": True, "message": body.message}


@app.post("/postcheck", response_model=PostcheckResponse)
def postcheck(body: PostcheckRequest):
    masked = sec.mask_sensitive_data(body.text)
    encrypted = sec.encrypt_data(masked).decode("utf-8")
    return PostcheckResponse(masked=masked, encrypted=encrypted)
