"""FastAPI entry point for the illustration-reference Agent."""

from fastapi import FastAPI

app = FastAPI(title="Illustration Reference Agent API")


@app.get("/health")
def health() -> dict[str, str]:
    """Return a deployment-safe status without calling external services."""

    return {"status": "ok", "service": "illustration-reference-agent"}
