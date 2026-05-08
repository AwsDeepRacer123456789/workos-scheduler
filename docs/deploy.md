# Deployment

## Local Development

## Local Control Plane Setup

This section is the fastest way to run the current Python control plane on your machine.

Prerequisite:
- Python 3

1. Install dependencies:

```bash
python3 -m pip install -r control_plane/requirements.txt
```

2. Run control-plane tests:

```bash
python3 -m pytest control_plane/tests
```

3. Run the API:

```bash
python3 -m uvicorn control_plane.api:app --reload
```

4. Open API docs:
- `http://127.0.0.1:8000/docs`

5. Health endpoint:
- `http://127.0.0.1:8000/health`

Notes for deployment planning:
- This setup is local-only and **not Dockerized yet**.
- It is **not connected yet** to Postgres, Kafka, Redis, or Go workers.
- Those integrations will be added later as the deployment path matures.

### Docker Compose Setup

TODO: Create docker-compose.yml with:
- Postgres database
- Redis instance
- Message broker (RabbitMQ or Redis Streams)
- Control plane API (Python FastAPI)
- Worker processes (Go)

### Running Locally

TODO: Document commands to:
- Start all services: `docker-compose up`
- Run migrations: `python manage.py migrate`
- Seed test data: `python scripts/seed.py`
- View logs: `docker-compose logs -f`

## Cloud Deployment (AWS)

### Infrastructure Overview

- **Control Plane**: Containerized Python service
- **Worker Plane**: Containerized Go services
- **Database**: AWS RDS Postgres (multi-AZ for HA)
- **Cache/Broker**: AWS ElastiCache Redis or managed message broker
- **Load Balancer**: Application Load Balancer for API
- **Container Orchestration**: TBD (ECS Fargate vs EKS) - see ADR-0002

### Infrastructure as Code

All infrastructure defined in Terraform:
- VPC and networking
- RDS Postgres instances
- ElastiCache Redis
- ECS/EKS clusters
- Load balancers
- IAM roles and policies
- Secrets Manager

### Deployment Process

TODO: Document CI/CD pipeline:
1. Code changes trigger build
2. Docker images built and pushed to ECR
3. Terraform plan/apply for infra changes
4. Blue-green or rolling deployment for services
5. Health checks and rollback procedures

## Container Orchestration Decision

We will decide between ECS Fargate and EKS in a later ADR (ADR-0002). Factors to consider:
- Team expertise
- Cost
- Operational complexity
- Scaling requirements
- Integration with other AWS services
