import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.app.routes import chat_router

app = FastAPI(
    title="MarIA - Agent Backend",
    description="Backend para assistente virtual de processos judiciais (SGPJ)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


app.include_router(chat_router)

__all__ = ["app"]
