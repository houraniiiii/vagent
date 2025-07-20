from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import jwt
import bcrypt
import os
import logging
from datetime import datetime, timedelta
import asyncio
from pathlib import Path
import json

from config_manager import ConfigManager
from agent_manager import AgentManager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Agent Management API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-jwt-key-change-this-in-production")
JWT_ALGORITHM = "HS256"

# Global instances
config_manager = ConfigManager()
agent_manager = AgentManager(config_manager)

# Pydantic models
class ConfigUpdate(BaseModel):
    agent_settings: Optional[Dict[str, Any]] = None
    llm_configs: Optional[Dict[str, Any]] = None
    stt_configs: Optional[Dict[str, Any]] = None
    tts_configs: Optional[Dict[str, Any]] = None
    telephony: Optional[Dict[str, Any]] = None
    integrations: Optional[Dict[str, Any]] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    username: str
    role: str
    permissions: List[str]

class StatusResponse(BaseModel):
    state: str
    pid: Optional[int] = None
    start_time: Optional[str] = None
    uptime: Optional[str] = None
    restart_count: int = 0
    error_message: Optional[str] = None

class MetricsResponse(BaseModel):
    uptime: str
    memory_usage: float
    cpu_usage: float
    status: str

# User management (In production, use a proper database)
USERS_DB = {
    "admin": {
        "password_hash": bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()),
        "role": "admin",
        "permissions": ["read", "write", "restart", "config", "logs"]
    },
    "operator": {
        "password_hash": bcrypt.hashpw("operator123".encode(), bcrypt.gensalt()),
        "role": "operator", 
        "permissions": ["read", "restart"]
    }
}

# Authentication functions
def verify_password(plain_password: str, hashed_password: bytes) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = USERS_DB.get(username)
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        
        return {
            "username": username,
            "role": user["role"],
            "permissions": user["permissions"]
        }
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_permission(permission: str):
    def permission_checker(current_user: dict = Depends(get_current_user)):
        if permission not in current_user["permissions"]:
            raise HTTPException(
                status_code=403, 
                detail=f"Permission '{permission}' required"
            )
        return current_user
    return permission_checker

# API Endpoints

@app.post("/auth/login")
async def login(login_request: LoginRequest):
    """Authenticate user and return access token"""
    user = USERS_DB.get(login_request.username)
    if not user or not verify_password(login_request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": login_request.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": login_request.username,
            "role": user["role"],
            "permissions": user["permissions"]
        }
    }

@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return UserResponse(**current_user)

@app.get("/agent/status", response_model=StatusResponse)
async def get_agent_status(current_user: dict = Depends(require_permission("read"))):
    """Get current agent status"""
    status = agent_manager.get_status()
    metrics = agent_manager.get_metrics()
    
    return StatusResponse(
        state=status.get("state", "unknown"),
        pid=status.get("pid"),
        start_time=status.get("start_time"),
        uptime=metrics.get("uptime"),
        restart_count=status.get("restart_count", 0),
        error_message=status.get("error_message")
    )

@app.post("/agent/start")
async def start_agent(current_user: dict = Depends(require_permission("restart"))):
    """Start the voice agent"""
    result = agent_manager.start_agent()
    if result["success"]:
        return {"message": result["message"], "status": result.get("status")}
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/agent/stop")
async def stop_agent(current_user: dict = Depends(require_permission("restart"))):
    """Stop the voice agent"""
    result = agent_manager.stop_agent()
    if result["success"]:
        return {"message": result["message"], "status": result.get("status")}
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/agent/restart")
async def restart_agent(background_tasks: BackgroundTasks, current_user: dict = Depends(require_permission("restart"))):
    """Restart the voice agent"""
    def restart_task():
        result = agent_manager.restart_agent()
        logger.info(f"Restart result: {result}")
    
    background_tasks.add_task(restart_task)
    return {"message": "Agent restart initiated"}

@app.get("/agent/metrics", response_model=MetricsResponse)
async def get_agent_metrics(current_user: dict = Depends(require_permission("read"))):
    """Get agent performance metrics"""
    metrics = agent_manager.get_metrics()
    return MetricsResponse(**metrics)

@app.get("/agent/logs")
async def get_agent_logs(
    lines: int = 100,
    current_user: dict = Depends(require_permission("logs"))
):
    """Get recent agent logs"""
    logs = agent_manager.get_logs(lines)
    return {"logs": logs}

@app.get("/config")
async def get_config(current_user: dict = Depends(require_permission("read"))):
    """Get current configuration"""
    return config_manager.config

@app.put("/config")
async def update_config(
    config_update: ConfigUpdate,
    current_user: dict = Depends(require_permission("config"))
):
    """Update agent configuration"""
    try:
        # Convert Pydantic model to dict, excluding None values
        updates = config_update.dict(exclude_none=True)
        
        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        config_manager.update_config(updates)
        
        # Validate the new configuration
        validation_results = config_manager.validate_config()
        
        return {
            "message": "Configuration updated successfully",
            "validation": validation_results,
            "config": config_manager.config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")

@app.post("/config/validate")
async def validate_config(current_user: dict = Depends(require_permission("read"))):
    """Validate current configuration"""
    validation_results = config_manager.validate_config()
    return {
        "validation_results": validation_results,
        "is_valid": all(validation_results.values())
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agent_status": agent_manager.get_status()["state"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)