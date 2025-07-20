from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import asyncio
import logging
from datetime import datetime
import jwt
import bcrypt
import os

from customer_manager import CustomerManager, CustomerConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Agent Master Console API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
JWT_SECRET = os.getenv("MASTER_JWT_SECRET", "master-console-jwt-secret-change-in-production")

# Global instances
customer_manager = CustomerManager()

# Pydantic models
class CustomerCreateRequest(BaseModel):
    customer_id: str
    customer_name: str
    ec2_instance_id: str
    ssh_key_path: str
    agent_config: Optional[Dict[str, Any]] = None

class CustomerUpdateRequest(BaseModel):
    customer_name: Optional[str] = None
    agent_config: Optional[Dict[str, Any]] = None

class ConfigDeployRequest(BaseModel):
    customer_ids: List[str]
    config: Dict[str, Any]

class BulkActionRequest(BaseModel):
    customer_ids: List[str]
    action: str  # 'start', 'stop', 'restart'

class LoginRequest(BaseModel):
    username: str
    password: str

# Master console user management
MASTER_USERS = {
    "master_admin": {
        "password_hash": bcrypt.hashpw("master_admin_2024!".encode(), bcrypt.gensalt()),
        "role": "master_admin",
        "permissions": ["all"]
    }
}

def verify_master_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        username = payload.get("sub")
        if username not in MASTER_USERS:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, **MASTER_USERS[username]}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/auth/login")
async def master_login(login_request: LoginRequest):
    """Authenticate master console user"""
    user = MASTER_USERS.get(login_request.username)
    if not user or not bcrypt.checkpw(login_request.password.encode(), user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = jwt.encode(
        {"sub": login_request.username, "exp": datetime.utcnow().timestamp() + 86400},
        JWT_SECRET,
        algorithm="HS256"
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": login_request.username,
            "role": user["role"],
            "permissions": user["permissions"]
        }
    }

@app.get("/customers")
async def list_customers(current_user: dict = Depends(verify_master_user)):
    """List all customers"""
    customers = customer_manager.list_customers()
    return {"customers": [customer.__dict__ for customer in customers]}

@app.post("/customers")
async def add_customer(
    customer_request: CustomerCreateRequest,
    current_user: dict = Depends(verify_master_user)
):
    """Add a new customer"""
    success = customer_manager.add_customer(
        customer_id=customer_request.customer_id,
        customer_name=customer_request.customer_name,
        ec2_instance_id=customer_request.ec2_instance_id,
        ssh_key_path=customer_request.ssh_key_path,
        agent_config=customer_request.agent_config
    )
    
    if success:
        return {"message": "Customer added successfully", "customer_id": customer_request.customer_id}
    else:
        raise HTTPException(status_code=400, detail="Failed to add customer")

@app.get("/customers/{customer_id}")
async def get_customer(
    customer_id: str,
    current_user: dict = Depends(verify_master_user)
):
    """Get customer details"""
    customer = customer_manager.get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"customer": customer.__dict__}

@app.put("/customers/{customer_id}")
async def update_customer(
    customer_id: str,
    update_request: CustomerUpdateRequest,
    current_user: dict = Depends(verify_master_user)
):
    """Update customer configuration"""
    customer = customer_manager.get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if update_request.customer_name:
        customer.customer_name = update_request.customer_name
    
    if update_request.agent_config:
        customer.agent_config.update(update_request.agent_config)
    
    customer.last_updated = datetime.now().isoformat()
    customer_manager.save_customers()
    
    return {"message": "Customer updated successfully"}

@app.delete("/customers/{customer_id}")
async def remove_customer(
    customer_id: str,
    current_user: dict = Depends(verify_master_user)
):
    """Remove a customer"""
    if customer_id in customer_manager.customers:
        del customer_manager.customers[customer_id]
        customer_manager.save_customers()
        return {"message": "Customer removed successfully"}
    else:
        raise HTTPException(status_code=404, detail="Customer not found")

@app.get("/customers/{customer_id}/status")
async def get_customer_status(
    customer_id: str,
    current_user: dict = Depends(verify_master_user)
):
    """Get detailed status for a customer"""
    status = await customer_manager.check_instance_status(customer_id)
    return {"status": status}

@app.get("/status/all")
async def get_all_customer_status(current_user: dict = Depends(verify_master_user)):
    """Get status for all customers"""
    statuses = await customer_manager.bulk_status_check()
    return {"statuses": statuses}

@app.post("/customers/{customer_id}/ec2/start")
async def start_customer_instance(
    customer_id: str,
    current_user: dict = Depends(verify_master_user)
):
    """Start EC2 instance for a customer"""
    success = customer_manager.start_ec2_instance(customer_id)
    if success:
        return {"message": f"EC2 instance start initiated for {customer_id}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to start instance")

@app.post("/customers/{customer_id}/ec2/stop")
async def stop_customer_instance(
    customer_id: str,
    current_user: dict = Depends(verify_master_user)
):
    """Stop EC2 instance for a customer"""
    success = customer_manager.stop_ec2_instance(customer_id)
    if success:
        return {"message": f"EC2 instance stop initiated for {customer_id}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to stop instance")

@app.post("/customers/{customer_id}/agent/restart")
async def restart_customer_agent(
    customer_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_master_user)
):
    """Restart voice agent for a customer"""
    async def restart_task():
        success = await customer_manager.restart_customer_agent(customer_id)
        logger.info(f"Agent restart for {customer_id}: {'success' if success else 'failed'}")
    
    background_tasks.add_task(restart_task)
    return {"message": f"Agent restart initiated for {customer_id}"}

@app.post("/config/deploy")
async def deploy_config_to_customers(
    deploy_request: ConfigDeployRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_master_user)
):
    """Deploy configuration to multiple customers"""
    async def deploy_task():
        results = {}
        for customer_id in deploy_request.customer_ids:
            success = await customer_manager.deploy_config_to_customer(
                customer_id, deploy_request.config
            )
            results[customer_id] = "success" if success else "failed"
        logger.info(f"Config deployment results: {results}")
    
    background_tasks.add_task(deploy_task)
    return {
        "message": "Configuration deployment initiated",
        "target_customers": deploy_request.customer_ids
    }

@app.post("/bulk-actions")
async def perform_bulk_action(
    bulk_request: BulkActionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_master_user)
):
    """Perform bulk actions on multiple customers"""
    async def bulk_task():
        results = {}
        
        for customer_id in bulk_request.customer_ids:
            try:
                if bulk_request.action == "restart":
                    success = await customer_manager.restart_customer_agent(customer_id)
                elif bulk_request.action == "start":
                    success = customer_manager.start_ec2_instance(customer_id)
                elif bulk_request.action == "stop":
                    success = customer_manager.stop_ec2_instance(customer_id)
                else:
                    success = False
                
                results[customer_id] = "success" if success else "failed"
            except Exception as e:
                results[customer_id] = f"error: {str(e)}"
        
        logger.info(f"Bulk action '{bulk_request.action}' results: {results}")
    
    background_tasks.add_task(bulk_task)
    return {
        "message": f"Bulk {bulk_request.action} action initiated",
        "target_customers": bulk_request.customer_ids
    }

@app.get("/metrics/overview")
async def get_metrics_overview(current_user: dict = Depends(verify_master_user)):
    """Get overview metrics for all customers"""
    statuses = await customer_manager.bulk_status_check()
    
    overview = {
        "total_customers": len(customer_manager.customers),
        "running_instances": 0,
        "active_agents": 0,
        "failed_instances": 0,
        "customers": []
    }
    
    for status in statuses:
        if isinstance(status, dict) and "error" not in status:
            if status.get("ec2_status") == "running":
                overview["running_instances"] += 1
            
            if status.get("agent_status") == "running":
                overview["active_agents"] += 1
            
            if status.get("ec2_status") in ["stopped", "stopping", "terminated"]:
                overview["failed_instances"] += 1
            
            overview["customers"].append({
                "customer_id": status.get("customer_id"),
                "customer_name": status.get("customer_name"),
                "ec2_status": status.get("ec2_status"),
                "agent_status": status.get("agent_status"),
                "metrics": status.get("metrics", {})
            })
    
    return overview

@app.get("/health")
async def health_check():
    """Health check for master console"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_customers": len(customer_manager.customers)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)