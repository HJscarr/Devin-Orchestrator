from fastapi import FastAPI

from app.routers import triage, approve, status, webhook

app = FastAPI(
    title="Devin Issue Orchestrator",
    description=(
        "Automated GitHub issue triage and resolution for FinServ Co, "
        "powered by Devin AI."
    ),
    version="1.0.0",
)

app.include_router(triage.router)
app.include_router(approve.router)
app.include_router(status.router)
app.include_router(webhook.router)


@app.get("/health")
def health():
    return {"status": "ok"}
