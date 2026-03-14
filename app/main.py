import logging

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.routers import triage, approve, status, webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Devin Issue Orchestrator",
    description=(
        "Automated GitHub issue triage and resolution for FinServ Co, "
        "powered by Devin AI."
    ),
    version="1.0.0",
)

logger.info("Devin Issue Orchestrator starting up")

app.include_router(triage.router)
app.include_router(approve.router)
app.include_router(status.router)
app.include_router(webhook.router)


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/health")
def health():
    return {"status": "ok"}
