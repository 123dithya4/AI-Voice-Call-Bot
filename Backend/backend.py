from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
import httpx
import os
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta
import asyncio
import secrets
import re

# Import database models and functions
from database import get_db, init_db, User, Call, Session as DBSession

# Initialize FastAPI app
app = FastAPI(title="Vapi Call Tracking System")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Configuration
VAPI_API_KEY = os.getenv("VAPI_API_KEY")
VAPI_PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID")
VAPI_BASE_URL = "https://api.vapi.ai"
# Keep model overrides complete: Vapi validates the provider and model when
# assistantOverrides.model is present. These defaults match api.py's assistant
# configuration and can be changed for deployments using a different model.
VAPI_MODEL_PROVIDER = os.getenv("VAPI_MODEL_PROVIDER", "openai")
VAPI_MODEL_NAME = os.getenv("VAPI_MODEL_NAME", "gpt-3.5-turbo")
SESSION_EXPIRE_HOURS = 24

# Models
class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    
    @validator('username')
    def username_valid(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username can only contain letters, numbers, and underscores')
        return v
    
    @validator('password')
    def password_valid(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters')
        
        # FIXED: Check the byte length instead of character length for bcrypt compatibility
        if len(v.encode('utf-8')) > 72:
            raise ValueError('Password is too long and cannot be hashed (must be less than 72 bytes)')
            
        return v

class LoginRequest(BaseModel):
    username: str
    password: str

class CallRequest(BaseModel):
    phone_number: str
    prompt: str


def _parse_vapi_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None


def _update_call_from_vapi(call: Call, data: dict):
    """Copy provider state into our local record without erasing known values."""
    call.status = data.get("status") or call.status
    call.ended_reason = data.get("endedReason") or call.ended_reason
    call.started_at = _parse_vapi_datetime(data.get("startedAt")) or call.started_at
    call.ended_at = _parse_vapi_datetime(data.get("endedAt")) or call.ended_at
    duration = data.get("durationSeconds")
    if duration is not None:
        call.duration = int(duration)
    artifact = data.get("artifact") or {}
    call.recording_url = data.get("recordingUrl") or artifact.get("recordingUrl") or call.recording_url
    call.transcript = data.get("transcript") or artifact.get("transcript") or call.transcript
    if data.get("cost") is not None:
        call.cost = str(data["cost"])


async def _fetch_vapi_call(client, call_id: str):
    response = await client.get(
        f"{VAPI_BASE_URL}/call/{call_id}",
        headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
        timeout=15.0,
    )
    if response.status_code != 200:
        return None, f"Vapi returned HTTP {response.status_code}"
    try:
        data = response.json()
    except ValueError:
        return None, "Vapi returned an invalid call response"
    if not isinstance(data, dict):
        return None, "Vapi returned an invalid call response"
    return data, None

# Authentication helper functions
def create_session_token() -> str:
    return secrets.token_urlsafe(32)

def create_user_session(db: Session, user_id: int, ip: str = None, user_agent: str = None) -> str:
    token = create_session_token()
    expires_at = datetime.utcnow() + timedelta(hours=SESSION_EXPIRE_HOURS)
    
    session = DBSession(
        session_token=token,
        user_id=user_id,
        expires_at=expires_at,
        ip_address=ip,
        user_agent=user_agent
    )
    db.add(session)
    db.commit()
    return token

def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    
    session = db.query(DBSession).filter(
        DBSession.session_token == token,
        DBSession.expires_at > datetime.utcnow()
    ).first()
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    
    return user

# Helper function to serve files
def serve_file(filename: str):
    file_path = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(file_path):
        if filename.endswith('.css'):
            return FileResponse(file_path, media_type="text/css")
        elif filename.endswith('.js'):
            return FileResponse(file_path, media_type="application/javascript")
        else:
            return FileResponse(file_path, media_type="text/html")
    raise HTTPException(status_code=404, detail=f"{filename} not found")

# Startup event
@app.on_event("startup")
async def startup_event():
    init_db()
    print("🚀 Database initialized and ready!")

# Root route
@app.get("/")
async def root():
    return serve_file("frontend.html")

# Serve HTML pages
@app.get("/home.html")
async def serve_home():
    return serve_file("home.html")

@app.get("/recordings.html")
async def serve_recordings():
    return serve_file("recordings.html")

@app.get("/call-now.html")
async def serve_call_now():
    return serve_file("call-now.html")

@app.get("/login.html")
async def serve_login():
    return serve_file("frontend.html")

@app.get("/frontend.html")
async def serve_frontend():
    return serve_file("frontend.html")

# Serve CSS and JS
@app.get("/styles.css")
async def serve_styles():
    return serve_file("styles.css")

@app.get("/app.js")
async def serve_app_js():
    return serve_file("app.js")

# Authentication Routes
@app.post("/api/auth/register")
async def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        # Check if username exists
        existing_user = db.query(User).filter(User.username == request.username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        # Check if email exists
        existing_email = db.query(User).filter(User.email == request.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # FIXED: Better error handling for password hashing
        try:
            hashed_pwd = User.hash_password(request.password)
            print(f"✅ Password hashed successfully, length: {len(hashed_pwd)}")
        except ValueError as e:
            # This will now catch the error from the User.hash_password static method
            raise HTTPException(status_code=400, detail=str(e))
        
        new_user = User(
            username=request.username,
            email=request.email,
            hashed_password=hashed_pwd,
            full_name=request.full_name
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        print(f"✅ User registered: {new_user.username}")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "User registered successfully",
                "user": {
                    "id": new_user.id,
                    "username": new_user.username,
                    "email": new_user.email,
                    "full_name": new_user.full_name
                }
            }
        )
    except HTTPException:
        # Re-raise HTTPException to let FastAPI handle it
        raise
    except Exception as e:
        print(f"❌ Registration error: {str(e)}")
        db.rollback() # Rollback transaction on any other error
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during registration.")

@app.post("/api/auth/login")
async def login(
    request_data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        user = db.query(User).filter(or_(User.username == request_data.username, User.email == request_data.username)).first()
        
        if not user or not user.verify_password(request_data.password):
            print(f"❌ Failed login attempt for user: {request_data.username}")
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")
        
        user.last_login = datetime.utcnow()
        
        token = create_user_session(
            db,
            user.id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")
        )
        
        db.commit() # Commit last_login update and new session
        
        print(f"✅ User logged in: {user.username}")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "token": token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "is_admin": user.is_admin
                }
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during login.")

@app.post("/api/auth/logout")
async def logout(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    try:
        if authorization and authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "")
            session = db.query(DBSession).filter(DBSession.session_token == token).first()
            if session:
                db.delete(session)
                db.commit()
        
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Logged out successfully"}
        )
    except Exception as e:
        print(f"Logout error: {str(e)}")
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Logged out"}
        )

@app.get("/api/auth/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "user": {
                "id": current_user.id,
                "username": current_user.username,
                "email": current_user.email,
                "full_name": current_user.full_name,
                "is_admin": current_user.is_admin,
                "created_at": current_user.created_at.isoformat()
            }
        }
    )

# ... (The rest of your /api/calls routes remain the same) ...

# Call Routes (Protected)
@app.post("/api/calls/initiate")
async def initiate_call(
    call_request: CallRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    phone_number = re.sub(r"[\s()-]", "", call_request.phone_number)
    if not re.fullmatch(r"\+[1-9]\d{7,14}", phone_number):
        raise HTTPException(
            status_code=400,
            detail="Enter a valid international phone number, such as +918714835696 (no spaces)."
        )
    print(f"User {current_user.username} initiating call to ***{phone_number[-4:]}")
    
    if not VAPI_API_KEY:
        raise HTTPException(status_code=500, detail="VAPI_API_KEY is missing from .env")
    if not VAPI_PHONE_NUMBER_ID or not VAPI_ASSISTANT_ID:
        raise HTTPException(status_code=500, detail="Set VAPI_PHONE_NUMBER_ID and VAPI_ASSISTANT_ID in .env")

    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Bearer {VAPI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "phoneNumberId": VAPI_PHONE_NUMBER_ID,
                "assistantId": VAPI_ASSISTANT_ID,
                "customer": {
                    "number": phone_number,
                },
                "assistantOverrides": {
                    "firstMessage": call_request.prompt,
                    "model": {
                        "provider": VAPI_MODEL_PROVIDER,
                        "model": VAPI_MODEL_NAME,
                        "messages": [
                            {
                                "role": "system",
                                "content": call_request.prompt
                            }
                        ]
                    }
                }
            }
            
            response = await client.post(
                f"{VAPI_BASE_URL}/call",
                headers=headers,
                json=payload,
                timeout=30.0
            )
            
            if response.status_code in (200, 201):
                call_data = response.json()
                vapi_call_id = call_data.get("id")
                if not vapi_call_id:
                    raise HTTPException(status_code=502, detail="Vapi accepted the request but returned no call ID")
                
                # Save to database
                new_call = Call(
                    call_id=vapi_call_id,
                    user_id=current_user.id,
                    phone_number=phone_number,
                    prompt=call_request.prompt,
                    status=call_data.get("status") or "queued",
                    ended_reason=call_data.get("endedReason")
                )
                _update_call_from_vapi(new_call, call_data)
                db.add(new_call)
                db.commit()
                db.refresh(new_call)
                
                print(f"✅ Call {vapi_call_id} saved to database")
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "call_id": vapi_call_id,
                        "data": call_data,
                        "message": "Vapi accepted the call request. Check call status to confirm whether it connected."
                    }
                )
            else:
                error_detail = response.text
                try:
                    error_json = response.json()
                    if isinstance(error_json, dict):
                        error_detail = error_json.get("message") or error_json.get("error") or str(error_json)
                except ValueError:
                    pass
                safe_error = str(error_detail).replace(phone_number, "[redacted phone]")[:1200]
                print(f"Vapi rejected call request ({response.status_code}): {safe_error}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Vapi API error: {safe_error}"
                )
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/calls")
async def get_all_calls(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if current_user.is_admin:
            calls = db.query(Call).order_by(Call.created_at.desc()).all()
        else:
            calls = db.query(Call).filter(
                Call.user_id == current_user.id
            ).order_by(Call.created_at.desc()).all()
        
        # Refresh non-terminal calls so the list reflects what Vapi actually reports.
        # Terminal calls remain cached and do not generate repeated provider requests.
        sync_errors = {}
        if VAPI_API_KEY:
            pending = [call for call in calls if call.status not in {"ended", "completed", "failed"}]
            if pending:
                try:
                    semaphore = asyncio.Semaphore(8)

                    async def fetch_limited(call_id):
                        async with semaphore:
                            return await _fetch_vapi_call(client, call_id)

                    async with httpx.AsyncClient() as client:
                        results = await asyncio.gather(*(
                            fetch_limited(call.call_id) for call in pending
                        ), return_exceptions=True)
                    for call, result in zip(pending, results):
                        if isinstance(result, tuple) and result[0]:
                            _update_call_from_vapi(call, result[0])
                        elif isinstance(result, tuple):
                            sync_errors[call.call_id] = result[1]
                        else:
                            sync_errors[call.call_id] = "Could not reach Vapi to refresh this call"
                    db.commit()
                except Exception as sync_error:
                    db.rollback()
                    print(f"Could not refresh call statuses from Vapi: {sync_error}")
        else:
            for call in calls:
                if call.status not in {"ended", "completed", "failed"}:
                    sync_errors[call.call_id] = "VAPI_API_KEY is not configured"

        calls_data = []
        for call in calls:
            calls_data.append({
                "id": call.call_id,
                "phone_number": call.phone_number,
                "prompt": call.prompt,
                "status": call.status,
                "ended_reason": call.ended_reason,
                "sync_error": sync_errors.get(call.call_id),
                "duration": call.duration,
                "created_at": call.created_at.isoformat() if call.created_at else None,
                "started_at": call.started_at.isoformat() if call.started_at else None,
                "ended_at": call.ended_at.isoformat() if call.ended_at else None,
                "recording_url": call.recording_url,
                "user": call.user.username
            })
        
        return JSONResponse(
            status_code=200,
            content={"success": True, "calls": calls_data}
        )
    except Exception as e:
        print(f"Error getting calls: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calls/{call_id}")
async def get_call_details(
    call_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    call = db.query(Call).filter(Call.call_id == call_id).first()
    
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    
    if not current_user.is_admin and call.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not VAPI_API_KEY:
        raise HTTPException(status_code=503, detail="VAPI_API_KEY is not configured; showing provider details is unavailable")
    try:
        async with httpx.AsyncClient() as client:
            vapi_data, sync_error = await _fetch_vapi_call(client, call_id)
        if not vapi_data:
            raise HTTPException(status_code=502, detail=f"Could not refresh call details: {sync_error}")
        _update_call_from_vapi(call, vapi_data)
        db.commit()
        return JSONResponse(status_code=200, content={
            "success": True,
            "call": {**vapi_data, "prompt": call.prompt, "user": call.user.username},
        })
    except HTTPException:
        raise
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Could not reach Vapi to refresh call details: {error}")

@app.delete("/api/calls/{call_id}")
async def delete_call(
    call_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    call = db.query(Call).filter(Call.call_id == call_id).first()
    
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    
    if not current_user.is_admin and call.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    db.delete(call)
    db.commit()
    
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Call deleted successfully"}
    )


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 Starting Vapi Call Tracking Server with Database...")
    print("=" * 60)
    print(f"📡 Backend API: http://localhost:8000")
    print(f"🌐 Frontend: http://localhost:8000/login.html")
    print(f"📚 API Docs: http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
