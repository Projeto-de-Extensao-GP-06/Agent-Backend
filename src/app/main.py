import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.app.routes import chat_router, auth_router

app = FastAPI(
    title="MarIA - Agent Backend",
    description="Backend para assistente virtual de processos judiciais (SGPJ)",
    version="1.0.0",
)

# Configuração de CORS - origens específicas (igual ao Backend Java)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Create React App
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


app.include_router(chat_router)
app.include_router(auth_router)

__all__ = ["app"]
