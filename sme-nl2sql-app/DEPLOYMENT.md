# SME NL2SQL Application – Deployment Guide

## Quick Start

**For production (Google Cloud Run):**
```bash
# 1. Set up GCP project and AlloyDB instance
# 2. Initialize database schema
# 3. Build and push Docker image
# 4. Deploy to Cloud Run with environment variables
```

---

## Prerequisites

### 1. Google Cloud Project Setup

```bash
# Create or select a GCP project
gcloud config set project YOUR_GCP_PROJECT_ID

# Enable required APIs
gcloud services enable aiplatform.googleapis.com
gcloud services enable alloydb.googleapis.com
gcloud services enable cloudrun.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

### 2. AlloyDB Instance

You should have an existing AlloyDB instance. Verify:

```bash
# List your AlloyDB clusters (replace PROJECT_ID, REGION)
gcloud alloydb clusters list --project=YOUR_PROJECT_ID

# Get cluster details
gcloud alloydb clusters describe YOUR_CLUSTER_ID \
  --region=YOUR_REGION \
  --project=YOUR_PROJECT_ID
```

**Note:** The application assumes:
- Database named `postgres` (or configure in `ALLOYDB_DB`)
- User `postgres` (or configure in `ALLOYDB_USER`)
- Schema initialized via `sql/init.sql`
- pgvector and google_ml_integration extensions enabled

### 3. Authentication

**For local development:**
- Use [AlloyDB Auth Proxy](https://cloud.google.com/alloydb/docs/auth-proxy/overview)
- Download the proxy and run it:
  ```bash
  ./cloud_sql_proxy -instances=PROJECT_ID:REGION:CLUSTER/INSTANCE_ID=tcp:5432
  ```

**For Cloud Run (recommended):**
- Use AlloyDB Private Service Connect or IAM database authentication
- The application will use Application Default Credentials (ADC) from the Cloud Run service account

---

## Local Development Setup

### 1. Clone and Install Dependencies

```bash
git clone <repo>
cd sme-nl2sql-app

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
# Copy the template
cp .env.example .env

# Edit .env with your values
# - ALLOYDB_HOST: 127.0.0.1 (AlloyDB Auth Proxy)
# - ALLOYDB_PASSWORD: your database password
# - GCP_PROJECT: your GCP project ID
# - GCP_REGION: matching your AlloyDB region
```

### 3. Initialize AlloyDB Schema (First Time Only)

```bash
# Ensure your .env is configured
# Then run the setup script
python scripts/setup_schema.py --csv data/financial_dataset_SME.csv
```

This script:
- Creates the schema (`sme_risk`)
- Creates tables and views
- Enables pgvector and google_ml_integration
- Loads data from the CSV
- Creates indexes on common filter columns

### 4. Start AlloyDB Auth Proxy

In a separate terminal:

```bash
# Download proxy (if not already done)
# https://cloud.google.com/alloydb/docs/auth-proxy/install

./cloud_sql_proxy -instances=PROJECT_ID:REGION:CLUSTER/INSTANCE_ID=tcp:5432
```

### 5. Run Locally

```bash
# In the virtual environment terminal
python main.py
```

The app will start on `http://localhost:8080`

### 6. Test the Endpoints

**Health check:**
```bash
curl http://localhost:8080/api/health
# { "status": "ok" }
```

**Readiness check:**
```bash
curl http://localhost:8080/api/readiness
# { "status": "ready" }  or  { "status": "unavailable", "detail": "..." }
```

**NL to SQL query:**
```bash
curl -X POST http://localhost:8080/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Which sectors have the highest distress rate?"}'

# Response:
# {
#   "question": "Which sectors have the highest distress rate?",
#   "generated_sql": "SELECT ...",
#   "results": [ ... ],
#   "cached": false
# }
```

**Pre-built analytics:**
```bash
curl http://localhost:8080/api/distress/summary
curl http://localhost:8080/api/distress/by-segment
```

**Dashboard UI:**
```
Open http://localhost:8080 in your browser
```

---

## Cloud Run Deployment

### 1. Build Docker Image

```bash
# Option A: Build locally and push to Artifact Registry
docker build -t gcr.io/YOUR_PROJECT_ID/sme-nl2sql:latest .
docker push gcr.io/YOUR_PROJECT_ID/sme-nl2sql:latest

# Option B: Use Cloud Build (no local Docker needed)
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/sme-nl2sql:latest
```

### 2. Create Cloud Run Service

```bash
gcloud run deploy sme-nl2sql \
  --image gcr.io/YOUR_PROJECT_ID/sme-nl2sql:latest \
  --platform managed \
  --region YOUR_REGION \
  --memory 1Gi \
  --cpu 1 \
  --set-env-vars \
    ALLOYDB_HOST=ALLOYDB_PRIVATE_IP,\
    ALLOYDB_PORT=5432,\
    ALLOYDB_DB=postgres,\
    ALLOYDB_USER=postgres,\
    ALLOYDB_PASSWORD=YOUR_PASSWORD,\
    ALLOYDB_SSLMODE=require,\
    GCP_PROJECT=YOUR_PROJECT_ID,\
    GCP_REGION=YOUR_REGION,\
    GEMINI_MODEL=gemini-2.0-flash,\
    EMBEDDING_MODEL=text-embedding-005,\
    CACHE_SIMILARITY_THRESHOLD=0.88,\
    DB_POOL_MAX=10
```

**Alternative: Use a secrets file**

```bash
# Create a .env.cloud file with production values
# gcloud secrets create sme-nl2sql-env --data-file=.env.cloud

gcloud run deploy sme-nl2sql \
  --image gcr.io/YOUR_PROJECT_ID/sme-nl2sql:latest \
  --platform managed \
  --region YOUR_REGION \
  --memory 1Gi \
  --set-env-vars ALLOYDB_HOST=PRIVATE_IP,...
```

### 3. Enable Private Service Connect (Optional but Recommended)

```bash
# This connects Cloud Run to AlloyDB without exposing public IPs
# Requires VPC Connector setup
gcloud run deploy sme-nl2sql \
  --image gcr.io/YOUR_PROJECT_ID/sme-nl2sql:latest \
  --vpc-connector=YOUR_CONNECTOR_NAME \
  --region YOUR_REGION
```

### 4. Verify Deployment

```bash
# Get the Cloud Run service URL
gcloud run services describe sme-nl2sql --region YOUR_REGION

# Test health endpoint
curl https://YOUR_SERVICE_URL/api/health

# Test readiness endpoint
curl https://YOUR_SERVICE_URL/api/readiness

# Test a query
curl -X POST https://YOUR_SERVICE_URL/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How many SMEs are in distress?"}'
```

### 5. Enable Auto-Scaling

Adjust based on your traffic:

```bash
gcloud run deploy sme-nl2sql \
  --update-config \
  --min-instances=1 \
  --max-instances=10 \
  --concurrency=80
```

---

## Environment Variable Validation Checklist

Before deployment, verify all environment variables are correctly set:

- [ ] **ALLOYDB_HOST**: Reachable from deployment location
  ```bash
  nc -zv $ALLOYDB_HOST $ALLOYDB_PORT
  ```

- [ ] **ALLOYDB_USER / ALLOYDB_PASSWORD**: Valid credentials
  ```bash
  psql -h $ALLOYDB_HOST -U $ALLOYDB_USER -d $ALLOYDB_DB -c "SELECT 1"
  ```

- [ ] **Database schema initialized**: Tables and views exist
  ```bash
  psql -h $ALLOYDB_HOST -U $ALLOYDB_USER -d $ALLOYDB_DB -c \
    "SELECT table_name FROM information_schema.tables WHERE table_schema='sme_risk'"
  ```

- [ ] **pgvector extension**: Created and enabled
  ```bash
  psql -h $ALLOYDB_HOST -U $ALLOYDB_USER -d $ALLOYDB_DB -c \
    "SELECT * FROM pg_extension WHERE extname='vector'"
  ```

- [ ] **query_cache table**: Exists and accessible
  ```bash
  psql -h $ALLOYDB_HOST -U $ALLOYDB_USER -d $ALLOYDB_DB -c \
    "SELECT 1 FROM sme_risk.query_cache LIMIT 1"
  ```

- [ ] **google_ml_integration extension**: Created
  ```bash
  psql -h $ALLOYDB_HOST -U $ALLOYDB_USER -d $ALLOYDB_DB -c \
    "SELECT * FROM pg_extension WHERE extname='google_ml_integration'"
  ```

- [ ] **GCP_PROJECT**: Valid and accessible
  ```bash
  gcloud config get-value project
  ```

- [ ] **Vertex AI models available**:
  ```bash
  # Check Gemini
  gcloud ai language models list --filter="name:*gemini*"

  # Check embeddings
  gcloud ai language models list --filter="name:*text-embedding*"
  ```

---

## Health Probes

Cloud Run uses these probes to manage the service:

**Liveness Probe** (restarts if fails):
```
GET /api/health
Expects: 200 OK with { "status": "ok" }
```

**Readiness Probe** (removes from load balancer if fails):
```
GET /api/readiness
Expects: 200 OK with { "status": "ready" }
        503 Service Unavailable if database is unreachable
```

These are configured automatically if you add them to your `app.yaml` or Cloud Run service definition:

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: sme-nl2sql
spec:
  template:
    spec:
      containers:
      - image: gcr.io/YOUR_PROJECT_ID/sme-nl2sql:latest
        livenessProbe:
          httpGet:
            path: /api/health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 60
        readinessProbe:
          httpGet:
            path: /api/readiness
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 30
```

---

## Troubleshooting

### Issue: "Connection refused" on database

**Cause:** AlloyDB Auth Proxy not running or database unreachable.

**Solution:**
```bash
# Check Auth Proxy is running
ps aux | grep cloud_sql_proxy

# Restart it
./cloud_sql_proxy -instances=PROJECT_ID:REGION:CLUSTER/INSTANCE_ID=tcp:5432

# Test connection
nc -zv 127.0.0.1 5432
```

### Issue: "Query cache table not found"

**Cause:** Schema not initialized.

**Solution:**
```bash
# Run the setup script
python scripts/setup_schema.py --csv data/financial_dataset_SME.csv
```

### Issue: "Gemini model not found" or "Embedding model not found"

**Cause:** Model names are incorrect or not enabled in Vertex AI.

**Solution:**
```bash
# List available models
gcloud ai language models list

# Check your region supports the model
gcloud ai language models describe gemini-2.0-flash --region=YOUR_REGION
```

### Issue: Cloud Run returns 500 on /api/ask

**Cause:** Check logs for details.

**Solution:**
```bash
# View recent logs
gcloud run services logs read sme-nl2sql --region YOUR_REGION --limit 50

# Or tail in real-time
gcloud alpha run services logs tail sme-nl2sql --region YOUR_REGION
```

---

## Performance Tuning

### Connection Pool

Adjust `DB_POOL_MAX` based on concurrency:

- **Local dev**: `2-5` (small resource footprint)
- **Small Cloud Run** (1 instance, 1 CPU): `5-10`
- **Large Cloud Run** (multiple instances): `15-30` per instance

```bash
# Update on deployed Cloud Run service
gcloud run deploy sme-nl2sql --update-config --set-env-vars DB_POOL_MAX=20
```

### Semantic Cache Tuning

**Similarity Threshold** (`CACHE_SIMILARITY_THRESHOLD`):

- **0.85**: Aggressive caching, more false positives, fewer Gemini calls (~70% savings)
- **0.88**: Balanced, recommended default (~50% savings)
- **0.92**: Conservative, high quality, fewer cache hits (~30% savings)

Adjust based on query quality feedback:

```bash
gcloud run deploy sme-nl2sql --update-config \
  --set-env-vars CACHE_SIMILARITY_THRESHOLD=0.92
```

### Gunicorn Workers/Threads

The Docker image runs:
```
gunicorn --workers=1 --threads=4 --timeout=120
```

For higher concurrency, modify `Dockerfile`:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "8", "--timeout", "120", "main:app"]
```

---

## Monitoring & Observability

### Cloud Run Metrics

```bash
# View invocations
gcloud monitoring metrics read "serverless.googleapis.com/invocations" \
  --filter='resource.service_name="sme-nl2sql"' \
  --region YOUR_REGION

# View latency
gcloud monitoring metrics read "serverless.googleapis.com/execution_times" \
  --filter='resource.service_name="sme-nl2sql"'
```

### Custom Logging

The application logs to stdout/stderr. Cloud Run captures these automatically:

```bash
# View application logs
gcloud run services logs read sme-nl2sql
```

### Query Cache Statistics

Monitor cache effectiveness:

```bash
gcloud run exec sme-nl2sql -- psql \
  -h $ALLOYDB_HOST \
  -U $ALLOYDB_USER \
  -d $ALLOYDB_DB \
  -c "SELECT COUNT(*) as total, AVG(hit_count) as avg_hits FROM sme_risk.query_cache"
```

---

## Rollback

If a deployment has issues:

```bash
# View recent revisions
gcloud run revisions list --service=sme-nl2sql --region YOUR_REGION

# Route traffic to a previous revision
gcloud run services update-traffic sme-nl2sql \
  --to-revisions REVISION_NAME=100 \
  --region YOUR_REGION
```

---

## Security Best Practices

1. **Use IAM authentication** instead of passwords when possible
2. **Store secrets** in Google Secret Manager (not in .env)
3. **Enable audit logging** for AlloyDB and Cloud Run
4. **Use Private Service Connect** to avoid public IPs
5. **Set request size limits** to prevent abuse (default: 1MB in app)
6. **Monitor and alert** on error rates and latency

---

## Next Steps

1. Test locally following "Local Development Setup"
2. Deploy to Cloud Run following "Cloud Run Deployment"
3. Monitor the service in Cloud Console
4. Tune performance thresholds based on real usage
5. Set up alerts for 5xx errors and high latency

For issues or questions, consult the troubleshooting section or review application logs.
