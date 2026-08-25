from fastapi import FastAPI
from app.agent.agent import criar_agente

app = FastAPI()

agent = criar_agente()

