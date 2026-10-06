from fastapi import FastAPI

from younique.api.factory import public

app = FastAPI(title="Younique MCP")


@app.get("/healthz")
@public
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
