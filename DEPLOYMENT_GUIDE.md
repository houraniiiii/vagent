# Voice Agent Management Console - Deployment Guide

## Architecture Overview

This system provides a production-ready management console for multiple voice agent instances across different EC2 servers for 5 customers. The architecture consists of:

### 1. Master Console (Central Management)
- **Master Console API** (Port 9000): Manages all customer instances
- **Frontend Console** (Port 3000): React-based UI for management
- **Customer Manager**: Orchestrates deployments and configurations

### 2. Customer Instances (Per Customer EC2)
- **Voice Agent**: LiveKit-based voice agent
- **Management API** (Port 8000): Individual instance management
- **Configuration Manager**: Dynamic configuration handling
- **Agent Manager**: Process lifecycle management

## Hardware Requirements

### Master Console Server
- **Instance Type**: t3.large or better
- **CPU**: 2+ vCPUs
- **RAM**: 8GB+
- **Storage**: 50GB SSD
- **Network**: VPC with internet access
- **OS**: Amazon Linux 2 or Ubuntu 20.04+

### Customer Instance Servers (x5)
- **Instance Type**: t3.medium or better
- **CPU**: 2+ vCPUs  
- **RAM**: 4GB+
- **Storage**: 20GB SSD
- **Network**: VPC with internet access
- **OS**: Amazon Linux 2
- **Voice Processing**: Optimized for real-time audio

### Network Architecture
```
Internet Gateway
    |
Application Load Balancer (HTTPS)
    |
VPC (10.0.0.0/16)
    |
├── Public Subnet (Master Console)
│   └── Master Console Server (10.0.1.10)
│
└── Private Subnets (Customer Instances)
    ├── Customer 1 Instance (10.0.2.10)
    ├── Customer 2 Instance (10.0.2.11)
    ├── Customer 3 Instance (10.0.2.12)
    ├── Customer 4 Instance (10.0.2.13)
    └── Customer 5 Instance (10.0.2.14)
```

## Security Implementation

### 1. Network Security
- VPC with private subnets for customer instances
- Security Groups with minimal required ports
- NAT Gateway for outbound internet access
- Application Load Balancer with SSL/TLS termination

### 2. Authentication & Authorization
- JWT-based authentication
- Role-based access control (RBAC)
- API key management for service-to-service communication
- Multi-factor authentication (recommended)

### 3. Data Security
- Environment variables for sensitive data
- AWS Secrets Manager integration
- Encrypted EBS volumes
- Regular security updates

### 4. API Security
- Rate limiting
- Input validation
- CORS configuration
- Request logging and monitoring

## Step-by-Step Deployment

### Phase 1: AWS Infrastructure Setup

#### 1.1 Create VPC and Networking
```bash
# Create VPC
aws ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=voice-agent-vpc}]'

# Create Internet Gateway
aws ec2 create-internet-gateway --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=voice-agent-igw}]'

# Create Public Subnet (Master Console)
aws ec2 create-subnet --vpc-id <VPC_ID> --cidr-block 10.0.1.0/24 --availability-zone us-east-1a

# Create Private Subnets (Customer Instances)
aws ec2 create-subnet --vpc-id <VPC_ID> --cidr-block 10.0.2.0/24 --availability-zone us-east-1a
```

#### 1.2 Create Security Groups
```bash
# Master Console Security Group
aws ec2 create-security-group --group-name master-console-sg --description "Master Console Security Group" --vpc-id <VPC_ID>

# Add rules for Master Console
aws ec2 authorize-security-group-ingress --group-id <SG_ID> --protocol tcp --port 22 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id <SG_ID> --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id <SG_ID> --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id <SG_ID> --protocol tcp --port 3000 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id <SG_ID> --protocol tcp --port 9000 --cidr 0.0.0.0/0
```

#### 1.3 Create IAM Roles
```bash
# Create IAM role for instances
aws iam create-role --role-name VoiceAgentInstanceRole --assume-role-policy-document file://ec2-trust-policy.json

# Attach policies
aws iam attach-role-policy --role-name VoiceAgentInstanceRole --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-role-policy --role-name VoiceAgentInstanceRole --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

# Create instance profile
aws iam create-instance-profile --instance-profile-name VoiceAgentInstanceProfile
aws iam add-role-to-instance-profile --instance-profile-name VoiceAgentInstanceProfile --role-name VoiceAgentInstanceRole
```

### Phase 2: Master Console Deployment

#### 2.1 Launch Master Console Instance
```bash
# Launch EC2 instance
aws ec2 run-instances \
    --image-id ami-0c02fb55956c7d316 \
    --count 1 \
    --instance-type t3.large \
    --key-name your-key-pair \
    --security-group-ids <MASTER_SG_ID> \
    --subnet-id <PUBLIC_SUBNET_ID> \
    --associate-public-ip-address \
    --iam-instance-profile Name=VoiceAgentInstanceProfile \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=voice-agent-master-console}]'
```

#### 2.2 Setup Master Console
```bash
# SSH into master console instance
ssh -i your-key.pem ec2-user@<MASTER_CONSOLE_IP>

# Install dependencies
sudo yum update -y
sudo yum install -y git python3.12 python3.12-pip nodejs npm nginx

# Clone repository
git clone https://github.com/KIPPS-AI/continental-re-vb.git
cd continental-re-vb

# Setup Python environment
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements_backend.txt

# Install additional dependencies for master console
pip install boto3 paramiko aiohttp pyyaml

# Setup environment variables
cat > .env << 'EOF'
# AWS Configuration
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1

# Master Console JWT Secret
MASTER_JWT_SECRET=your-super-secret-master-jwt-key

# API Keys for deployment
GROQ_API_KEY=your-groq-key
OPENAI_API_KEY=your-openai-key
ELEVENLABS_API_KEY=your-elevenlabs-key
DEEPGRAM_API_KEY=your-deepgram-key
PINECONE_API_KEY=your-pinecone-key

# LiveKit Configuration
LIVEKIT_URL=your-livekit-url
LIVEKIT_API_KEY=your-livekit-api-key
LIVEKIT_API_SECRET=your-livekit-api-secret
EOF

# Setup frontend
cd frontend
npm install
npm run build
cd ..

# Create systemd service for master API
sudo tee /etc/systemd/system/master-console-api.service > /dev/null <<EOF
[Unit]
Description=Voice Agent Master Console API
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/continental-re-vb
Environment=PATH=/home/ec2-user/continental-re-vb/.venv/bin
ExecStart=/home/ec2-user/continental-re-vb/.venv/bin/python master_console_api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable master-console-api
sudo systemctl start master-console-api

# Configure nginx
sudo tee /etc/nginx/conf.d/master-console.conf > /dev/null <<EOF
server {
    listen 80;
    server_name _;
    
    # Frontend
    location / {
        root /home/ec2-user/continental-re-vb/frontend/dist;
        try_files \$uri \$uri/ /index.html;
    }
    
    # API
    location /api/ {
        proxy_pass http://127.0.0.1:9000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo systemctl restart nginx
```

### Phase 3: Customer Instance Deployment

#### 3.1 Create Customer Configuration Files
```bash
# Create customer configurations
mkdir -p /home/ec2-user/customer-configs

# Customer 1 Configuration
cat > /home/ec2-user/customer-configs/customer1.yaml <<EOF
customer_id: "customer1"
customer_name: "Customer One"
key_pair_name: "your-key-pair"
instance_type: "t3.medium"
ami_id: "ami-0c02fb55956c7d316"
iam_role: "VoiceAgentInstanceRole"

api_keys:
  groq: "your-groq-key"
  openai: "your-openai-key"
  elevenlabs: "your-elevenlabs-key"
  deepgram: "your-deepgram-key"
  pinecone: "your-pinecone-key"

livekit:
  url: "your-livekit-url"
  api_key: "your-livekit-api-key"
  api_secret: "your-livekit-api-secret"

aws:
  access_key_id: "your-access-key"
  secret_access_key: "your-secret-key"
  region: "us-east-1"
  s3_bucket: "your-s3-bucket"

jwt_secret: "customer1-jwt-secret"
EOF

# Repeat for customers 2-5 with different customer_id, customer_name, and jwt_secret
```

#### 3.2 Deploy Customer Instances
```bash
# Deploy all customer instances
for i in {1..5}; do
    echo "Deploying customer $i..."
    python infrastructure/deploy_customer.py --config customer-configs/customer$i.yaml --region us-east-1
    sleep 60  # Wait between deployments
done
```

#### 3.3 Register Customers in Master Console
```bash
# Add customers to master console
python -c "
from customer_manager import CustomerManager
import boto3

cm = CustomerManager()

# Get instance IDs (replace with actual instance IDs from deployment)
customers = [
    ('customer1', 'Customer One', 'i-1234567890abcdef0'),
    ('customer2', 'Customer Two', 'i-1234567890abcdef1'),
    ('customer3', 'Customer Three', 'i-1234567890abcdef2'),
    ('customer4', 'Customer Four', 'i-1234567890abcdef3'),
    ('customer5', 'Customer Five', 'i-1234567890abcdef4'),
]

for customer_id, name, instance_id in customers:
    cm.add_customer(
        customer_id=customer_id,
        customer_name=name,
        ec2_instance_id=instance_id,
        ssh_key_path='/home/ec2-user/.ssh/id_rsa'
    )
    print(f'Added {customer_id}')
"
```

### Phase 4: SSL/TLS Setup (Production)

#### 4.1 Create Application Load Balancer
```bash
# Create ALB
aws elbv2 create-load-balancer \
    --name voice-agent-alb \
    --subnets <PUBLIC_SUBNET_ID> <ANOTHER_PUBLIC_SUBNET_ID> \
    --security-groups <ALB_SECURITY_GROUP_ID>

# Create target group
aws elbv2 create-target-group \
    --name voice-agent-targets \
    --protocol HTTP \
    --port 80 \
    --vpc-id <VPC_ID> \
    --health-check-path /health

# Register master console instance
aws elbv2 register-targets \
    --target-group-arn <TARGET_GROUP_ARN> \
    --targets Id=<MASTER_CONSOLE_INSTANCE_ID>
```

#### 4.2 Setup SSL Certificate
```bash
# Request SSL certificate via ACM
aws acm request-certificate \
    --domain-name yourdomain.com \
    --domain-name *.yourdomain.com \
    --validation-method DNS

# Create HTTPS listener
aws elbv2 create-listener \
    --load-balancer-arn <ALB_ARN> \
    --protocol HTTPS \
    --port 443 \
    --certificates CertificateArn=<CERTIFICATE_ARN> \
    --default-actions Type=forward,TargetGroupArn=<TARGET_GROUP_ARN>
```

### Phase 5: Monitoring & Logging

#### 5.1 CloudWatch Setup
```bash
# Install CloudWatch agent on all instances
sudo yum install -y amazon-cloudwatch-agent

# Configure CloudWatch agent
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json > /dev/null <<EOF
{
    "logs": {
        "logs_collected": {
            "files": {
                "collect_list": [
                    {
                        "file_path": "/opt/voice-agent/voice-agent.log",
                        "log_group_name": "voice-agent-logs",
                        "log_stream_name": "{instance_id}"
                    }
                ]
            }
        }
    },
    "metrics": {
        "namespace": "VoiceAgent",
        "metrics_collected": {
            "cpu": {
                "measurement": ["cpu_usage_idle", "cpu_usage_iowait", "cpu_usage_system", "cpu_usage_user"],
                "metrics_collection_interval": 60
            },
            "disk": {
                "measurement": ["used_percent"],
                "metrics_collection_interval": 60,
                "resources": ["*"]
            },
            "mem": {
                "measurement": ["mem_used_percent"],
                "metrics_collection_interval": 60
            }
        }
    }
}
EOF

# Start CloudWatch agent
sudo amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s
```

## Usage Instructions

### 1. Access Master Console
1. Navigate to `https://yourdomain.com` or `http://<MASTER_CONSOLE_IP>`
2. Login with master credentials:
   - Username: `master_admin`
   - Password: `master_admin_2024!`

### 2. Manage Customers
- **View All Customers**: Dashboard shows all customer status
- **Add Customer**: Use the "Add Customer" form
- **Update Configuration**: Edit customer settings and deploy
- **Restart Agents**: Individual or bulk restart options
- **Monitor Performance**: Real-time metrics and logs

### 3. Configuration Management
- **Global Settings**: Apply settings to multiple customers
- **Customer-Specific**: Individual customer configurations
- **Validation**: Automatic configuration validation
- **Rollback**: Configuration version control

### 4. Monitoring & Alerts
- **Real-time Status**: Live customer and agent status
- **Performance Metrics**: CPU, memory, uptime tracking
- **Log Analysis**: Centralized log viewing
- **Alerts**: Email/SMS notifications for issues

## Maintenance & Operations

### Daily Operations
1. **Health Checks**: Monitor all customer instances
2. **Log Review**: Check for errors or warnings
3. **Performance Monitoring**: Track resource usage
4. **Backup Verification**: Ensure data backups are current

### Weekly Operations
1. **Security Updates**: Apply OS and dependency updates
2. **Performance Analysis**: Review metrics and optimize
3. **Configuration Backup**: Backup customer configurations
4. **Capacity Planning**: Monitor resource usage trends

### Monthly Operations
1. **Security Audit**: Review access logs and permissions
2. **Cost Optimization**: Analyze AWS costs and optimize
3. **Disaster Recovery Test**: Test backup and recovery procedures
4. **Documentation Update**: Keep documentation current

## Troubleshooting Guide

### Common Issues

#### 1. Agent Not Starting
```bash
# Check agent status
curl http://<CUSTOMER_IP>:8000/health

# Check logs
tail -f /opt/voice-agent/voice-agent.log

# Check service status
sudo systemctl status voice-agent-api
```

#### 2. Configuration Not Applied
```bash
# Verify configuration file
cat /opt/voice-agent/agent_config.json

# Check API connectivity
curl -H "Authorization: Bearer <TOKEN>" http://<CUSTOMER_IP>:8000/config

# Force restart
sudo systemctl restart voice-agent-api
```

#### 3. High Resource Usage
```bash
# Check system resources
htop
df -h
free -m

# Check voice agent process
ps aux | grep voice
```

### Recovery Procedures

#### 1. Instance Recovery
```bash
# Stop instance
aws ec2 stop-instances --instance-ids <INSTANCE_ID>

# Create AMI backup
aws ec2 create-image --instance-id <INSTANCE_ID> --name "voice-agent-backup-$(date +%Y%m%d)"

# Start instance
aws ec2 start-instances --instance-ids <INSTANCE_ID>
```

#### 2. Data Recovery
```bash
# Restore from S3 backup
aws s3 sync s3://your-backup-bucket/customer-configs/ ./customer-configs/

# Restore database
# (If using database for customer management)
```

## Security Best Practices

### 1. Access Control
- Use IAM roles with minimal permissions
- Implement MFA for admin accounts
- Regular access review and cleanup
- Audit trails for all actions

### 2. Network Security
- Private subnets for customer instances
- VPC flow logs enabled
- Regular security group audits
- WAF protection for public endpoints

### 3. Data Protection
- Encrypt data at rest and in transit
- Regular backups to S3
- Secrets management with AWS Secrets Manager
- Data retention policies

### 4. Monitoring
- Real-time security monitoring
- Automated threat detection
- Log aggregation and analysis
- Incident response procedures

## Cost Optimization

### Instance Sizing
- Right-size instances based on actual usage
- Use Reserved Instances for predictable workloads
- Implement auto-scaling for variable loads
- Regular cost analysis and optimization

### Storage Optimization
- Use appropriate storage types (gp3 vs gp2)
- Implement lifecycle policies for logs
- Regular cleanup of unused resources
- Monitor data transfer costs

### Automation
- Automated start/stop schedules
- Resource tagging for cost allocation
- Regular cost reports and alerts
- Optimization recommendations

This deployment guide provides a comprehensive roadmap for implementing a production-ready voice agent management console system. Follow each phase carefully and adapt the configurations to your specific requirements and security policies.