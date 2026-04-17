# SME NL2SQL – Natural Language to SQL Query Interface

A production-ready API that lets non-technical business users query SME financial distress data using plain English instead of SQL. Powered by Google Vertex AI Gemini 2.0 Flash and AlloyDB with semantic query caching.

## 🚀 Quick Start

### Local Development

1. **Install dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your GCP project, AlloyDB credentials, etc.
   ```

3. **Start AlloyDB Auth Proxy** (in a separate terminal)
   ```bash
   ./cloud_sql_proxy -instances=PROJECT_ID:REGION:CLUSTER/INSTANCE_ID=tcp:5432
   ```

4. **Run the app**
   ```bash
   python main.py
   # or with Gunicorn:
   gunicorn main:app --workers 1 --threads 4
   ```

5. **Test endpoints**
   ```bash
   # Health check
   curl http://localhost:8080/api/health

   # Ask a question
   curl -X POST http://localhost:8080/api/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "Which sectors have distress?"}'

   # Dashboard UI
   open http://localhost:8080
   ```

## 📋 Configuration

See [.env.example](.env.example) for all environment variables. Key settings:

- `ALLOYDB_HOST`, `ALLOYDB_USER`, `ALLOYDB_PASSWORD`: Database credentials
- `GCP_PROJECT`, `GCP_REGION`: Google Cloud configuration
- `GEMINI_MODEL`: LLM for SQL generation (default: `gemini-2.0-flash`)
- `EMBEDDING_MODEL`: For semantic caching similarity (default: `text-embedding-005`)
- `CACHE_SIMILARITY_THRESHOLD`: Tune cache hit rate (default: `0.88`)
- `DB_POOL_MAX`: Connection pool size (default: `5`)

## 🏗️ Architecture

```
User Query (Plain English)
    ↓
POST /api/ask (Flask)
    ↓
Cache Lookup (pgvector + AlloyDB)
    ├─ HIT → Return cached SQL
    ├─ MISS → Call Gemini 2.0 Flash
    │    ↓
    │    SQL Generation
    │    ↓
    │    Store in cache with embedding
    └─ Execute SQL on AlloyDB
    ↓
Return JSON (results + metadata)
```

## 📚 API Endpoints

### `POST /api/ask`
Generate and execute a natural-language query.

**Request:**
```json
{ "question": "Which sectors have the highest distress rate?" }
```

**Response (on cache hit):**
```json
{
  "question": "Which sectors have the highest distress rate?",
  "generated_sql": "SELECT ...",
  "results": [ {...}, ... ],
  "cached": true,
  "execution_time_ms": 45.3,
  "total_time_ms": 52.1
}
```

**Response (on error):**
```json
{
  "error": "Human-readable error",
  "code": "QUERY_ERROR",
  "details": "Technical details"
}
```

### `GET /api/distress/summary`
Pre-built endpoint: distress counts by label (Stable vs Distressed).

### `GET /api/distress/by-segment`
Pre-built endpoint: distress rates by sector, size, and revenue (top 50).

### `GET /api/health`
Liveness probe (always returns 200 if service is running).

### `GET /api/readiness`
Readiness probe (returns 200 if DB is accessible, 503 otherwise).

## 🐳 Docker & Cloud Run

### Build locally
```bash
docker build -t sme-nl2sql:latest .
docker run -e ALLOYDB_HOST=... -e GCP_PROJECT=... -p 8080:8080 sme-nl2sql:latest
```

### Deploy to Cloud Run
```bash
gcloud run deploy sme-nl2sql \
  --image gcr.io/YOUR_PROJECT_ID/sme-nl2sql:latest \
  --region us-central1 \
  --set-env-vars ALLOYDB_HOST=...,GCP_PROJECT=...
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

## 📊 Performance & Caching

### Semantic Query Cache

The system caches SQL queries based on semantic similarity (cosine distance via pgvector):

- **First query**: ~1-2 seconds (LLM call + SQL execution)
- **Similar query (from cache)**: ~50ms (DB lookup + execution)
- **Cache hit rate**: Typically 40-60% depending on query patterns

**Tuning cache similarity threshold:**
```bash
# More aggressive caching (may return wrong results occasionally)
export CACHE_SIMILARITY_THRESHOLD=0.85

# Conservative caching (high quality, fewer hits)
export CACHE_SIMILARITY_THRESHOLD=0.92
```

### Connection Pooling

Adjust `DB_POOL_MAX` based on concurrency:

- **Local dev**: 2-5 connections
- **Small Cloud Run** (1 instance): 5-10
- **High concurrency**: 15-30 per instance

## 🔒 Security

- ✅ **SQL Injection**: All queries use parameterized statements (psycopg)
- ✅ **Input validation**: Question length limits (1000 chars max)
- ✅ **Request size limits**: 1 MB max payload
- ✅ **Error sanitization**: Technical details excluded from client responses
- ✅ **SSL mode**: Required for production connections

## 📝 Logging

Logs are written to stdout (Cloud Run compatible). Set `LOG_LEVEL` environment variable:

```bash
export LOG_LEVEL=DEBUG  # Verbose logging
export LOG_LEVEL=INFO   # Default
export LOG_LEVEL=ERROR  # Only errors
```

## 🛠️ Development

### Running Tests

```bash
# Check syntax and types (requires pylance/pyright)
pylint app/ main.py

# Run integration tests (requires live AlloyDB)
python -m pytest tests/
```

### Project Structure

```
sme-nl2sql-app/
├── main.py              # Flask app factory & entry point
├── app/
│   ├── routes.py        # HTTP endpoints
│   ├── nl_query.py      # NL→SQL via Gemini + caching
│   ├── db.py            # Connection pool & SQL execution
│   └── __init__.py
├── templates/
│   └── index.html       # Dashboard UI
├── sql/
│   ├── init.sql         # Schema initialization
│   └── insert_data.sql  # (optional) data loading
├── scripts/
│   └── setup_schema.py  # CLI: load CSV into AlloyDB
├── data/
│   └── financial_dataset_SME.csv  # Training data
├── Dockerfile           # Cloud Run container
├── requirements.txt     # Python dependencies
├── .env.example         # Configuration template
├── DEPLOYMENT.md        # Deployment guide
└── README.md            # This file
```

## 🚨 Troubleshooting

**"Connection refused" on database:**
- Ensure AlloyDB Auth Proxy is running
- Verify `ALLOYDB_HOST` and `ALLOYDB_PORT` are correct

**"Gemini model not found":**
- Check `GEMINI_MODEL` environment variable
- Verify model is enabled in Vertex AI for your region

**"Query cache table not found":**
- Run `python scripts/setup_schema.py` to initialize schema

**High latency on first query:**
- This is expected (LLM call latency ~1-2s)
- Subsequent similar queries use cache (~50ms)

See [DEPLOYMENT.md](DEPLOYMENT.md#troubleshooting) for more troubleshooting steps.

## 📖 Further Reading

- [AlloyDB Documentation](https://cloud.google.com/alloydb/docs)
- [Vertex AI Gemini API](https://cloud.google.com/vertex-ai/docs/generative-ai/learn)
- [pgvector Guide](https://github.com/pgvector/pgvector)
- [Cloud Run Documentation](https://cloud.google.com/run/docs)

## 📄 License

[Add your license here]

## 👥 Contributors

Team SoloTude – Mark Samuel Nicasio, Chirag Ubnare
