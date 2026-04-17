# Quick Reference Card

## 🚀 Local Testing (30 seconds)

```bash
# 1. Start AlloyDB Auth Proxy (separate terminal)
./cloud_sql_proxy -instances=PROJECT:REGION:CLUSTER/INSTANCE=tcp:5432

# 2. Run app (main terminal)
python main.py

# 3. Test endpoints
curl http://localhost:8080/api/health
curl -X POST http://localhost:8080/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Which sectors have highest distress?"}'
```

## ☁️ Cloud Run Deployment (5 minutes)

```bash
# 1. Build
gcloud builds submit --tag gcr.io/YOUR_PROJECT/sme-nl2sql:latest

# 2. Deploy
gcloud run deploy sme-nl2sql \
  --image gcr.io/YOUR_PROJECT/sme-nl2sql:latest \
  --region us-central1 \
  --set-env-vars ALLOYDB_HOST=PRIVATE_IP,ALLOYDB_USER=postgres,...
```

See DEPLOYMENT.md for complete command and all variables.

## 📊 Monitoring

```bash
# Cache performance
curl https://YOUR_SERVICE/api/cache/stats

# Logs
gcloud run services logs read sme-nl2sql --limit 50

# Health
curl https://YOUR_SERVICE/api/health
curl https://YOUR_SERVICE/api/readiness
```

## 📋 Configuration

See `.env.example` for all 12 environment variables. Key ones:

- `ALLOYDB_HOST` — Database host (use Auth Proxy on local: 127.0.0.1)
- `GCP_PROJECT` — Your Google Cloud project ID
- `CACHE_SIMILARITY_THRESHOLD` — Tune cache hits (0.88 default)
- `DB_POOL_MAX` — Connection pool size (5 default)

## 🔧 Files to Know

| File | Purpose |
|------|---------|
| `main.py` | Flask entry point |
| `app/routes.py` | HTTP endpoints (7 total) |
| `app/nl_query.py` | NL→SQL via Gemini + caching |
| `app/db.py` | Connection pool |
| `.env.example` | Configuration template |
| `DEPLOYMENT.md` | Production deployment guide |
| `README.md` | Full documentation |

## 🎯 API Endpoints Cheat Sheet

```bash
# Ask a question (main endpoint)
POST /api/ask
Body: {"question": "..."}
Response: {question, generated_sql, results, cached, execution_time_ms, total_time_ms}

# Pre-built analytics
GET /api/distress/summary          → Distress by label
GET /api/distress/by-segment       → Distress by sector/size/revenue

# Monitoring
GET /api/cache/stats              → Cache performance
GET /api/health                   → Liveness probe
GET /api/readiness               → Readiness probe

# UI
GET /                             → Dashboard
```

## ⚠️ Common Issues

| Issue | Solution |
|-------|----------|
| "Connection refused" | Start AlloyDB Auth Proxy |
| "Schema not found" | Run `python scripts/setup_schema.py` |
| "Query cache not found" | Initialize schema (run setup_schema.py) |
| Slow first query | Expected (1-2s for Gemini), cache hits are ~50ms |
| High error rate | Check logs: `gcloud run services logs read sme-nl2sql` |

See DEPLOYMENT.md troubleshooting section for more.

## 📞 Success Criteria

✅ All endpoints respond 200 OK
✅ Health probe returns {"status": "ok"}
✅ Readiness probe returns {"status": "ready"}
✅ NL2SQL query returns results in <2 seconds
✅ Second identical query returns in <100ms (cached)
✅ Cache stats shows hit_count > 0
✅ All errors return valid JSON with code field

## 🎓 What's New

✨ **Logging** — Structured logs for observability
✨ **Timing** — Response includes execution_time_ms, total_time_ms
✨ **Error Format** — Standard {error, code, details}
✨ **Validation** — Input length checks, content-type validation
✨ **Security** — Request size limits (1 MB)
✨ **Monitoring** — New /api/cache/stats endpoint
✨ **Documentation** — DEPLOYMENT.md, README.md, this card

---

**Ready to deploy?** → See DEPLOYMENT.md
**Need help?** → Check README.md or IMPLEMENTATION_COMPLETE.md
