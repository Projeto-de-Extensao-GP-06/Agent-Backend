from fastapi import FastAPI

# código temporário apenas para testar agente
from app.agent.agent import criar_agente
agent = criar_agente()

app = FastAPI()



