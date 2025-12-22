# Deployment Guide

## Overview

This guide covers deployment considerations and instructions for the Parcel MVP in production environments.

## Current Architecture

The current implementation is designed for development/single-server deployment:
- File-based tile caching
- In-memory spatial index
- Direct database connections
- No load balancing

## Production Considerations

### 1. Security

**Current Issues**:
- CORS allows all origins (`allow_origins=["*"]`)
- Database credentials hardcoded
- No authentication/authorization

**Recommendations**:
- Restrict CORS to specific domains
- Use environment variables for credentials
- Implement API authentication (JWT, OAuth, etc.)
- Use HTTPS in production
- Implement rate limiting

### 2. Performance

**Current Limitations**:
- Single server handles all requests
- File-based cache (not shared across instances)
- In-memory spatial index (limited by RAM)

**Optimizations**:
- Use Redis for distributed tile caching
- Implement CDN for tile distribution
- Use database connection pooling
- Consider horizontal scaling with load balancer

### 3. Database

**Current Setup**:
- Direct connections from application
- No connection pooling (except vector tile server)

**Recommendations**:
- Use connection pooling (PgBouncer)
- Set up database replication for read scaling
- Implement database backups
- Monitor query performance

## Deployment Options

### Option 1: Single Server Deployment

**Suitable for**: Small to medium traffic

**Components**:
- Backend API on single server
- PostgreSQL on same or separate server
- File-based tile cache
- Frontend served statically

**Steps**:

1. **Server Setup**:
```bash
# Install dependencies
sudo apt update
sudo apt install python3 python3-pip postgresql postgis nginx

# Clone repository
git clone <repository-url>
cd parcel_mvp
```

2. **Database Setup**:
```bash
# Create database and user
sudo -u postgres psql
CREATE DATABASE parcels_db;
CREATE USER parcel_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE parcels_db TO parcel_user;
\c parcels_db
CREATE EXTENSION postgis;
\q
```

3. **Application Setup**:
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run ETL
python etl/load_vellore.py
```

4. **Run with Systemd**:

Create `/etc/systemd/system/parcel-api.service`:
```ini
[Unit]
Description=Parcel MVP API
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/parcel_mvp/backend
Environment="PATH=/path/to/parcel_mvp/venv/bin"
ExecStart=/path/to/parcel_mvp/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable parcel-api
sudo systemctl start parcel-api
```

5. **Nginx Configuration**:

Create `/etc/nginx/sites-available/parcel-mvp`:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Tile proxy
    location /tiles/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_cache_valid 200 1h;
    }

    # Frontend
    location / {
        root /path/to/parcel_mvp/frontend/map-app;
        try_files $uri $uri/ /index.html;
    }
}
```

Enable and restart:
```bash
sudo ln -s /etc/nginx/sites-available/parcel-mvp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Option 2: Docker Deployment

**Suitable for**: Containerized environments

**Dockerfile Example** (`Dockerfile`):
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libgdal-dev \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY backend/ ./backend/
COPY etl/ ./etl/
COPY data/ ./data/

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Docker Compose Example** (`docker-compose.yml`):
```yaml
version: '3.8'

services:
  db:
    image: postgis/postgis:14-3.2
    environment:
      POSTGRES_DB: parcels_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/parcels_db
    depends_on:
      - db
    volumes:
      - ./backend/cache:/app/backend/cache

volumes:
  postgres_data:
```

### Option 3: Cloud Deployment

**Platforms**: AWS, Google Cloud, Azure, Heroku

**Considerations**:
- Use managed PostgreSQL (RDS, Cloud SQL, etc.)
- Use object storage for tile cache (S3, GCS, etc.)
- Use CDN for tile distribution (CloudFront, Cloud CDN, etc.)
- Use load balancer for API
- Use container orchestration (Kubernetes, ECS, etc.)

## Environment Variables

Create `.env` file for production:

```bash
# Database
DATABASE_URL=postgresql://user:password@host:port/database
DB_HOST=your-db-host
DB_PORT=5432
DB_NAME=parcels_db
DB_USER=parcel_user
DB_PASSWORD=secure_password

# API
API_HOST=0.0.0.0
API_PORT=8000

# CORS
ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com

# Cache
CACHE_DIR=/var/cache/parcel-tiles
CACHE_TYPE=filesystem  # or 'redis' for distributed

# Redis (if using)
REDIS_HOST=localhost
REDIS_PORT=6379
```

## Tile Caching Strategy

### Current: File-Based Cache

**Pros**:
- Simple implementation
- No additional dependencies
- Fast for single server

**Cons**:
- Not shared across instances
- Disk space management needed
- Not suitable for horizontal scaling

### Recommended: Redis Cache

**Benefits**:
- Distributed caching
- Shared across instances
- Automatic expiration
- Better performance

**Implementation** (future):
```python
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def get_tile_from_cache(z, x, y):
    key = f"tile:{z}:{x}:{y}"
    return redis_client.get(key)

def save_tile_to_cache(z, x, y, tile_data):
    key = f"tile:{z}:{x}:{y}"
    redis_client.setex(key, 3600, tile_data)  # 1 hour TTL
```

### CDN Distribution

For high traffic:
- Pre-generate tiles for common zoom levels
- Upload to CDN (CloudFront, Cloudflare, etc.)
- Serve tiles from CDN
- Generate on-demand for rare tiles

## Monitoring

### Application Monitoring

**Metrics to Track**:
- API response times
- Tile generation time
- Cache hit rate
- Database query performance
- Error rates

**Tools**:
- Prometheus + Grafana
- New Relic
- Datadog
- Application Insights

### Database Monitoring

**Metrics**:
- Connection pool usage
- Query performance
- Disk usage
- Replication lag (if applicable)

**Tools**:
- pg_stat_statements
- pgAdmin
- Cloud provider monitoring

### Logging

**Structured Logging**:
```python
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("Tile generated", extra={
    "z": z, "x": x, "y": y, "duration_ms": duration
})
```

**Log Aggregation**:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Splunk
- CloudWatch Logs
- Datadog Logs

## Backup Strategy

### Database Backups

**Automated Backups**:
```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d)
pg_dump -U postgres parcels_db > /backups/parcels_db_$DATE.sql
```

**Retention**: Keep 7 daily, 4 weekly, 12 monthly backups

### Tile Cache Backup

- Not critical (can be regenerated)
- Consider backing up if pre-generated
- Use version control for tile generation code

## Scaling

### Vertical Scaling

- Increase server resources (CPU, RAM, disk)
- Upgrade database instance
- Add more disk for cache

### Horizontal Scaling

**Requirements**:
- Shared cache (Redis)
- Load balancer
- Stateless application design
- Database connection pooling

**Architecture**:
```
Load Balancer
    ├── API Server 1
    ├── API Server 2
    └── API Server N
         ↓
    Shared Redis Cache
         ↓
    PostgreSQL (Primary + Replicas)
```

## Security Checklist

- [ ] Use HTTPS (SSL/TLS certificates)
- [ ] Restrict CORS origins
- [ ] Use environment variables for secrets
- [ ] Implement API authentication
- [ ] Set up firewall rules
- [ ] Regular security updates
- [ ] Database access restrictions
- [ ] Rate limiting
- [ ] Input validation
- [ ] SQL injection prevention (use parameterized queries)

## Performance Tuning

### Database

- Create appropriate indexes
- Analyze query plans
- Tune PostgreSQL configuration
- Use connection pooling

### Application

- Optimize tile generation
- Cache aggressively
- Use async operations where possible
- Monitor and optimize slow queries

### Infrastructure

- Use SSD storage for database
- Adequate RAM for spatial index
- Network optimization
- CDN for static assets

## Related Documentation

- [SETUP.md](SETUP.md) - Initial setup
- [CONFIG.md](CONFIG.md) - Configuration
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture

