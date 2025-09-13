from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as api_router
from starlette.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from dotenv import load_dotenv
load_dotenv()
app = FastAPI(
    title="Conversational Triage POC",
    version="0.1.0",
    description="Safe, non-diagnostic patient guidance via conversation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    data = generate_latest()  # default registry
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
app.include_router(api_router, prefix="/api")