#!/usr/bin/env python3
"""
Automated deployment script for new customer voice agent instances.
This script provisions EC2 instances and sets up the voice agent infrastructure.
"""

import boto3
import time
import argparse
import logging
import json
import subprocess
from pathlib import Path
from typing import Dict, Any
import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CustomerDeployment:
    def __init__(self, aws_region: str = "us-east-1"):
        self.aws_region = aws_region
        self.ec2 = boto3.client('ec2', region_name=aws_region)
        self.ec2_resource = boto3.resource('ec2', region_name=aws_region)
        
    def create_security_group(self, customer_id: str) -> str:
        """Create security group for the customer instance"""
        try:
            sg_name = f"voice-agent-{customer_id}-sg"
            
            # Check if security group already exists
            try:
                response = self.ec2.describe_security_groups(
                    GroupNames=[sg_name]
                )
                if response['SecurityGroups']:
                    logger.info(f"Security group {sg_name} already exists")
                    return response['SecurityGroups'][0]['GroupId']
            except self.ec2.exceptions.ClientError:
                pass
            
            # Create security group
            response = self.ec2.create_security_group(
                GroupName=sg_name,
                Description=f"Security group for voice agent {customer_id}",
                VpcId=self._get_default_vpc_id()
            )
            
            sg_id = response['GroupId']
            
            # Add inbound rules
            self.ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 22,
                        'ToPort': 22,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]  # SSH access
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 8000,
                        'ToPort': 8000,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]  # API access
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]  # HTTPS
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 80,
                        'ToPort': 80,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]  # HTTP
                    }
                ]
            )
            
            logger.info(f"Created security group: {sg_id}")
            return sg_id
            
        except Exception as e:
            logger.error(f"Error creating security group: {e}")
            raise
    
    def launch_instance(self, customer_config: Dict[str, Any]) -> str:
        """Launch EC2 instance for customer"""
        try:
            customer_id = customer_config['customer_id']
            
            # Create security group
            sg_id = self.create_security_group(customer_id)
            
            # User data script for instance initialization
            user_data = self._generate_user_data_script(customer_config)
            
            # Launch instance
            response = self.ec2.run_instances(
                ImageId=customer_config.get('ami_id', 'ami-0c02fb55956c7d316'),  # Amazon Linux 2
                MinCount=1,
                MaxCount=1,
                InstanceType=customer_config.get('instance_type', 't3.medium'),
                KeyName=customer_config['key_pair_name'],
                SecurityGroupIds=[sg_id],
                UserData=user_data,
                TagSpecifications=[
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {'Key': 'Name', 'Value': f'voice-agent-{customer_id}'},
                            {'Key': 'Customer', 'Value': customer_config['customer_name']},
                            {'Key': 'Environment', 'Value': 'production'},
                            {'Key': 'Project', 'Value': 'voice-agent'}
                        ]
                    }
                ],
                IamInstanceProfile={
                    'Name': customer_config.get('iam_role', 'VoiceAgentInstanceRole')
                }
            )
            
            instance_id = response['Instances'][0]['InstanceId']
            logger.info(f"Launched instance {instance_id} for customer {customer_id}")
            
            # Wait for instance to be running
            logger.info("Waiting for instance to be running...")
            waiter = self.ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=[instance_id])
            
            # Get instance details
            response = self.ec2.describe_instances(InstanceIds=[instance_id])
            instance = response['Reservations'][0]['Instances'][0]
            public_ip = instance.get('PublicIpAddress')
            private_ip = instance.get('PrivateIpAddress')
            
            logger.info(f"Instance is running. Public IP: {public_ip}, Private IP: {private_ip}")
            
            return instance_id
            
        except Exception as e:
            logger.error(f"Error launching instance: {e}")
            raise
    
    def setup_voice_agent(self, instance_id: str, customer_config: Dict[str, Any]) -> bool:
        """Setup voice agent on the instance"""
        try:
            # Wait for instance to be fully initialized
            logger.info("Waiting for instance initialization to complete...")
            time.sleep(120)  # Wait for user data script to complete
            
            # Verify the setup via API health check
            response = self.ec2.describe_instances(InstanceIds=[instance_id])
            instance = response['Reservations'][0]['Instances'][0]
            public_ip = instance.get('PublicIpAddress')
            
            if public_ip:
                import requests
                health_url = f"http://{public_ip}:8000/health"
                
                # Wait for API to be available
                for attempt in range(30):  # 5 minutes max
                    try:
                        response = requests.get(health_url, timeout=10)
                        if response.status_code == 200:
                            logger.info("Voice agent API is responding")
                            return True
                    except requests.exceptions.RequestException:
                        pass
                    
                    logger.info(f"Waiting for API... attempt {attempt + 1}/30")
                    time.sleep(10)
                
                logger.error("API did not become available within timeout")
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error setting up voice agent: {e}")
            return False
    
    def _get_default_vpc_id(self) -> str:
        """Get the default VPC ID"""
        try:
            response = self.ec2.describe_vpcs(
                Filters=[{'Name': 'is-default', 'Values': ['true']}]
            )
            if response['Vpcs']:
                return response['Vpcs'][0]['VpcId']
            else:
                raise Exception("No default VPC found")
        except Exception as e:
            logger.error(f"Error getting default VPC: {e}")
            raise
    
    def _generate_user_data_script(self, customer_config: Dict[str, Any]) -> str:
        """Generate user data script for instance initialization"""
        customer_id = customer_config['customer_id']
        
        script = f"""#!/bin/bash
set -e

# Update system
yum update -y

# Install required packages
yum install -y git python3.12 python3.12-pip docker nginx

# Start and enable services
systemctl start docker
systemctl enable docker
systemctl start nginx
systemctl enable nginx

# Add ec2-user to docker group
usermod -a -G docker ec2-user

# Create application directory
mkdir -p /opt/voice-agent
cd /opt/voice-agent

# Clone the repository (replace with your actual repo)
git clone https://github.com/KIPPS-AI/continental-re-vb.git .

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements_backend.txt

# Create environment file
cat > .env << 'EOF'
# API Keys (these should be provided securely)
GROQ_API_KEY={customer_config.get('api_keys', {}).get('groq', '')}
OPENAI_API_KEY={customer_config.get('api_keys', {}).get('openai', '')}
ELEVENLABS_API_KEY={customer_config.get('api_keys', {}).get('elevenlabs', '')}
DEEPGRAM_API_KEY={customer_config.get('api_keys', {}).get('deepgram', '')}
PINECONE_API_KEY={customer_config.get('api_keys', {}).get('pinecone', '')}

# LiveKit Configuration
LIVEKIT_URL={customer_config.get('livekit', {}).get('url', '')}
LIVEKIT_API_KEY={customer_config.get('livekit', {}).get('api_key', '')}
LIVEKIT_API_SECRET={customer_config.get('livekit', {}).get('api_secret', '')}

# AWS Configuration
AWS_ACCESS_KEY_ID={customer_config.get('aws', {}).get('access_key_id', '')}
AWS_SECRET_ACCESS_KEY={customer_config.get('aws', {}).get('secret_access_key', '')}
AWS_REGION={customer_config.get('aws', {}).get('region', 'us-east-1')}
S3_BUCKET={customer_config.get('aws', {}).get('s3_bucket', '')}

# JWT Secret
JWT_SECRET={customer_config.get('jwt_secret', 'default-jwt-secret-change-in-production')}
EOF

# Set permissions
chown -R ec2-user:ec2-user /opt/voice-agent
chmod 600 /opt/voice-agent/.env

# Create systemd service for the management API
cat > /etc/systemd/system/voice-agent-api.service << 'EOF'
[Unit]
Description=Voice Agent Management API
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/voice-agent
Environment=PATH=/opt/voice-agent/.venv/bin
ExecStart=/opt/voice-agent/.venv/bin/python management_api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
systemctl daemon-reload
systemctl enable voice-agent-api
systemctl start voice-agent-api

# Configure nginx as reverse proxy
cat > /etc/nginx/conf.d/voice-agent.conf << 'EOF'
server {{
    listen 80;
    server_name _;
    
    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
EOF

# Restart nginx
systemctl restart nginx

# Log completion
echo "Voice agent setup completed for customer {customer_id}" >> /var/log/user-data.log
"""
        return script

def main():
    parser = argparse.ArgumentParser(description='Deploy customer voice agent instance')
    parser.add_argument('--config', required=True, help='Customer configuration file (YAML)')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    
    args = parser.parse_args()
    
    # Load customer configuration
    with open(args.config, 'r') as f:
        customer_config = yaml.safe_load(f)
    
    deployment = CustomerDeployment(aws_region=args.region)
    
    try:
        # Launch instance
        instance_id = deployment.launch_instance(customer_config)
        
        # Setup voice agent
        if deployment.setup_voice_agent(instance_id, customer_config):
            logger.info(f"Successfully deployed voice agent for customer {customer_config['customer_id']}")
            logger.info(f"Instance ID: {instance_id}")
        else:
            logger.error("Voice agent setup failed")
            
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        raise

if __name__ == "__main__":
    main()