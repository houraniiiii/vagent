import boto3
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import paramiko
import asyncio
import aiohttp
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class CustomerConfig:
    customer_id: str
    customer_name: str
    ec2_instance_id: str
    instance_ip: str
    ssh_key_path: str
    api_port: int = 8000
    agent_config: Dict[str, Any] = None
    status: str = "inactive"
    last_updated: str = None

class CustomerManager:
    """Manages multiple customer instances and their voice agents"""
    
    def __init__(self, aws_region: str = "us-east-1"):
        self.aws_region = aws_region
        self.ec2_client = boto3.client('ec2', region_name=aws_region)
        self.customers_config_file = Path("customers_config.json")
        self.customers: Dict[str, CustomerConfig] = {}
        self.load_customers()
    
    def load_customers(self) -> None:
        """Load customer configurations from file"""
        try:
            if self.customers_config_file.exists():
                with open(self.customers_config_file, 'r') as f:
                    data = json.load(f)
                    for customer_id, config in data.items():
                        self.customers[customer_id] = CustomerConfig(**config)
                logger.info(f"Loaded {len(self.customers)} customer configurations")
            else:
                logger.info("No existing customer configurations found")
        except Exception as e:
            logger.error(f"Error loading customer configurations: {e}")
    
    def save_customers(self) -> None:
        """Save customer configurations to file"""
        try:
            data = {
                customer_id: asdict(customer) 
                for customer_id, customer in self.customers.items()
            }
            with open(self.customers_config_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Customer configurations saved")
        except Exception as e:
            logger.error(f"Error saving customer configurations: {e}")
    
    def add_customer(
        self, 
        customer_id: str, 
        customer_name: str, 
        ec2_instance_id: str,
        ssh_key_path: str,
        agent_config: Dict[str, Any] = None
    ) -> bool:
        """Add a new customer configuration"""
        try:
            # Get instance details from AWS
            response = self.ec2_client.describe_instances(
                InstanceIds=[ec2_instance_id]
            )
            
            if not response['Reservations']:
                logger.error(f"Instance {ec2_instance_id} not found")
                return False
            
            instance = response['Reservations'][0]['Instances'][0]
            instance_ip = instance.get('PublicIpAddress') or instance.get('PrivateIpAddress')
            
            if not instance_ip:
                logger.error(f"No IP address found for instance {ec2_instance_id}")
                return False
            
            customer_config = CustomerConfig(
                customer_id=customer_id,
                customer_name=customer_name,
                ec2_instance_id=ec2_instance_id,
                instance_ip=instance_ip,
                ssh_key_path=ssh_key_path,
                agent_config=agent_config or {},
                last_updated=datetime.now().isoformat()
            )
            
            self.customers[customer_id] = customer_config
            self.save_customers()
            
            logger.info(f"Added customer {customer_name} with instance {ec2_instance_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding customer: {e}")
            return False
    
    def get_customer(self, customer_id: str) -> Optional[CustomerConfig]:
        """Get customer configuration"""
        return self.customers.get(customer_id)
    
    def list_customers(self) -> List[CustomerConfig]:
        """List all customers"""
        return list(self.customers.values())
    
    async def check_instance_status(self, customer_id: str) -> Dict[str, Any]:
        """Check EC2 instance and agent status for a customer"""
        customer = self.get_customer(customer_id)
        if not customer:
            return {"error": "Customer not found"}
        
        try:
            # Check EC2 instance status
            response = self.ec2_client.describe_instances(
                InstanceIds=[customer.ec2_instance_id]
            )
            
            instance = response['Reservations'][0]['Instances'][0]
            ec2_status = instance['State']['Name']
            
            # Check agent status via API
            agent_status = "unknown"
            agent_metrics = {}
            
            if ec2_status == 'running':
                try:
                    async with aiohttp.ClientSession() as session:
                        url = f"http://{customer.instance_ip}:{customer.api_port}/health"
                        async with session.get(url, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                agent_status = data.get('agent_status', 'unknown')
                                
                                # Get detailed metrics
                                metrics_url = f"http://{customer.instance_ip}:{customer.api_port}/agent/metrics"
                                async with session.get(metrics_url, timeout=10) as metrics_response:
                                    if metrics_response.status == 200:
                                        agent_metrics = await metrics_response.json()
                            else:
                                agent_status = "api_unreachable"
                except Exception as e:
                    logger.warning(f"Could not reach agent API for {customer_id}: {e}")
                    agent_status = "api_error"
            
            return {
                "customer_id": customer_id,
                "customer_name": customer.customer_name,
                "ec2_status": ec2_status,
                "agent_status": agent_status,
                "instance_ip": customer.instance_ip,
                "metrics": agent_metrics,
                "last_checked": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error checking status for {customer_id}: {e}")
            return {
                "customer_id": customer_id,
                "error": str(e)
            }
    
    async def deploy_config_to_customer(self, customer_id: str, config: Dict[str, Any]) -> bool:
        """Deploy configuration changes to a customer's instance"""
        customer = self.get_customer(customer_id)
        if not customer:
            logger.error(f"Customer {customer_id} not found")
            return False
        
        try:
            # Update configuration via API
            async with aiohttp.ClientSession() as session:
                url = f"http://{customer.instance_ip}:{customer.api_port}/config"
                headers = {
                    'Authorization': f'Bearer {self._get_customer_api_token(customer_id)}',
                    'Content-Type': 'application/json'
                }
                
                async with session.put(url, json=config, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        logger.info(f"Configuration deployed to {customer_id}")
                        
                        # Update local customer config
                        customer.agent_config.update(config)
                        customer.last_updated = datetime.now().isoformat()
                        self.save_customers()
                        
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to deploy config to {customer_id}: {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error deploying config to {customer_id}: {e}")
            return False
    
    async def restart_customer_agent(self, customer_id: str) -> bool:
        """Restart a customer's voice agent"""
        customer = self.get_customer(customer_id)
        if not customer:
            logger.error(f"Customer {customer_id} not found")
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{customer.instance_ip}:{customer.api_port}/agent/restart"
                headers = {
                    'Authorization': f'Bearer {self._get_customer_api_token(customer_id)}',
                }
                
                async with session.post(url, headers=headers, timeout=60) as response:
                    if response.status == 200:
                        logger.info(f"Agent restart initiated for {customer_id}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to restart agent for {customer_id}: {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error restarting agent for {customer_id}: {e}")
            return False
    
    def start_ec2_instance(self, customer_id: str) -> bool:
        """Start EC2 instance for a customer"""
        customer = self.get_customer(customer_id)
        if not customer:
            return False
        
        try:
            self.ec2_client.start_instances(InstanceIds=[customer.ec2_instance_id])
            logger.info(f"Started EC2 instance for {customer_id}")
            return True
        except Exception as e:
            logger.error(f"Error starting instance for {customer_id}: {e}")
            return False
    
    def stop_ec2_instance(self, customer_id: str) -> bool:
        """Stop EC2 instance for a customer"""
        customer = self.get_customer(customer_id)
        if not customer:
            return False
        
        try:
            self.ec2_client.stop_instances(InstanceIds=[customer.ec2_instance_id])
            logger.info(f"Stopped EC2 instance for {customer_id}")
            return True
        except Exception as e:
            logger.error(f"Error stopping instance for {customer_id}: {e}")
            return False
    
    def _get_customer_api_token(self, customer_id: str) -> str:
        """Get API token for customer (implement proper token management)"""
        # In production, implement proper token management
        # For now, return a default token or implement customer-specific tokens
        return "your-customer-api-token"
    
    async def bulk_status_check(self) -> List[Dict[str, Any]]:
        """Check status for all customers"""
        tasks = [
            self.check_instance_status(customer_id) 
            for customer_id in self.customers.keys()
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)