from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.db import SessionLocal

app = FastAPI(title="Română B1 operational API", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT id FROM users LIMIT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
