import sys
from pathlib import Path

from fastapi import FastAPI

if __package__ is None or __package__ == "":
	sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.api.chat_router import router as chat_router

app = FastAPI()
app.include_router(chat_router)



