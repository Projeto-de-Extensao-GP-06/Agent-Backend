import asyncio

from rich import print

from app.service.agent_service import executarPipelineAgente


async def main():
    print("""
    Agent: Olá, eu sou a MarIA! A assistente virtual do SGPJ. Posso te ajudar de várias formas:
    - Analisar indicadores da dashboard do sistema;
    - Gerar um ICS para marcar um novo compromisso em sua agenda;
    - Analisar algum processo específico;

    É só me dizer!
""")

    while True:
        userInput = input("User: ")
        if userInput.lower() in ["exit", "quit"]:
            print("Exiting the agent.")
            break

        resposta = await executarPipelineAgente(
            mensagem=userInput,
            idSessao="local-session",
            dadosProcesso=None,
        )

        print(f"Agent: {resposta}")


if __name__ == "__main__":
    asyncio.run(main())