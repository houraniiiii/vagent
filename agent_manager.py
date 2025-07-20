import subprocess
import signal
import psutil
import time
import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime
from config_manager import ConfigManager

logger = logging.getLogger(__name__)

class AgentManager:
    """Manages voice agent process lifecycle"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.agent_process: Optional[subprocess.Popen] = None
        self.status_file = Path("agent_status.json")
        self.log_file = Path("agent_manager.log")
        
        # Setup logging
        handler = logging.FileHandler(self.log_file)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status"""
        try:
            if self.status_file.exists():
                with open(self.status_file, 'r') as f:
                    status = json.load(f)
            else:
                status = {
                    "state": "stopped",
                    "pid": None,
                    "start_time": None,
                    "last_restart": None,
                    "restart_count": 0,
                    "error_message": None
                }
            
            # Verify process is actually running
            if status["state"] == "running" and status["pid"]:
                if not psutil.pid_exists(status["pid"]):
                    status["state"] = "stopped"
                    status["pid"] = None
                    status["error_message"] = "Process not found"
                    self._save_status(status)
            
            return status
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {
                "state": "error",
                "error_message": str(e)
            }
    
    def start_agent(self, force_restart: bool = False) -> Dict[str, Any]:
        """Start the voice agent"""
        try:
            current_status = self.get_status()
            
            if current_status["state"] == "running" and not force_restart:
                return {
                    "success": False,
                    "message": "Agent is already running",
                    "status": current_status
                }
            
            if force_restart and current_status["state"] == "running":
                self.stop_agent()
                time.sleep(2)  # Give it time to fully stop
            
            # Start the agent process
            python_path = self._get_python_path()
            cmd = [python_path, "-m", "voice_agent_with_rag", "start"]
            
            self.agent_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.getcwd(),
                env=os.environ.copy()
            )
            
            # Wait a moment to check if process started successfully
            time.sleep(2)
            if self.agent_process.poll() is None:  # Process is still running
                status = {
                    "state": "running",
                    "pid": self.agent_process.pid,
                    "start_time": datetime.now().isoformat(),
                    "last_restart": datetime.now().isoformat(),
                    "restart_count": current_status.get("restart_count", 0) + 1,
                    "error_message": None
                }
                self._save_status(status)
                
                logger.info(f"Agent started successfully with PID {self.agent_process.pid}")
                return {
                    "success": True,
                    "message": "Agent started successfully",
                    "status": status
                }
            else:
                # Process failed to start
                stdout, stderr = self.agent_process.communicate()
                error_msg = f"Agent failed to start: {stderr.decode()}"
                logger.error(error_msg)
                
                status = {
                    "state": "error",
                    "pid": None,
                    "error_message": error_msg,
                    "last_restart": datetime.now().isoformat()
                }
                self._save_status(status)
                
                return {
                    "success": False,
                    "message": error_msg,
                    "status": status
                }
                
        except Exception as e:
            error_msg = f"Error starting agent: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
    
    def stop_agent(self) -> Dict[str, Any]:
        """Stop the voice agent"""
        try:
            current_status = self.get_status()
            
            if current_status["state"] != "running":
                return {
                    "success": True,
                    "message": "Agent is not running"
                }
            
            pid = current_status.get("pid")
            if pid and psutil.pid_exists(pid):
                try:
                    # Try graceful shutdown first
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(5)
                    
                    # Force kill if still running
                    if psutil.pid_exists(pid):
                        os.kill(pid, signal.SIGKILL)
                        time.sleep(2)
                    
                    logger.info(f"Agent stopped successfully (PID {pid})")
                except ProcessLookupError:
                    pass  # Process already dead
            
            status = {
                "state": "stopped",
                "pid": None,
                "stop_time": datetime.now().isoformat(),
                "restart_count": current_status.get("restart_count", 0),
                "error_message": None
            }
            self._save_status(status)
            
            return {
                "success": True,
                "message": "Agent stopped successfully",
                "status": status
            }
            
        except Exception as e:
            error_msg = f"Error stopping agent: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
    
    def restart_agent(self) -> Dict[str, Any]:
        """Restart the voice agent"""
        logger.info("Restarting agent...")
        return self.start_agent(force_restart=True)
    
    def get_logs(self, lines: int = 100) -> str:
        """Get recent agent logs"""
        try:
            log_path = self.config_manager.get("logging.file", "voice-agent.log")
            if os.path.exists(log_path):
                with open(log_path, 'r') as f:
                    all_lines = f.readlines()
                    return ''.join(all_lines[-lines:])
            return "No logs found"
        except Exception as e:
            return f"Error reading logs: {str(e)}"
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get agent performance metrics"""
        try:
            status = self.get_status()
            metrics = {
                "uptime": "0:00:00",
                "memory_usage": 0,
                "cpu_usage": 0,
                "status": status["state"]
            }
            
            if status["state"] == "running" and status.get("pid"):
                process = psutil.Process(status["pid"])
                
                # Calculate uptime
                if status.get("start_time"):
                    start_time = datetime.fromisoformat(status["start_time"])
                    uptime = datetime.now() - start_time
                    metrics["uptime"] = str(uptime).split('.')[0]  # Remove microseconds
                
                # Get resource usage
                metrics["memory_usage"] = process.memory_info().rss / 1024 / 1024  # MB
                metrics["cpu_usage"] = process.cpu_percent()
            
            return metrics
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return {
                "uptime": "0:00:00",
                "memory_usage": 0,
                "cpu_usage": 0,
                "status": "error",
                "error": str(e)
            }
    
    def _save_status(self, status: Dict[str, Any]) -> None:
        """Save status to file"""
        try:
            with open(self.status_file, 'w') as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving status: {e}")
    
    def _get_python_path(self) -> str:
        """Get the Python executable path"""
        venv_python = Path(".venv/bin/python")
        if venv_python.exists():
            return str(venv_python.absolute())
        return "python3"