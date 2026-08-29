from rich import print
from app.main import agent
from langchain.messages import HumanMessage

thread_config = {"configurable": {"thread_id": "1"}}

print(f"""Agent: Olá, eu sou a MarIA! A assitente virtual do SGPJ. Posso te ajudar de várias formas:
- Analisar indicadores da dashboard do sistema;
- Gerar um ICS para marcar um novo compromisso em sua agenda;
- Analisar algum processo específico;

É só me dizer!
""")

while True:
    user_input = input("User: ")
    if user_input.lower() in ["exit", "quit"]:
        print("Exiting the agent.")
        break
    response = agent.invoke({"messages": [HumanMessage(content=user_input)]}, thread_config)

    #Inverta os comentários para ver resposta completa ou somente o texto de resposta
    print(f"Agent: {response["messages"]}")

    # messages = response.get("messages", [])
    # last_message = messages[-1]
    # content = last_message.content
    # if isinstance(content, list):
    #     text = ""
    #     for item in content:
    #         if isinstance(item, dict) and "text" in item:
    #             text += item["text"]
    #     print(f"Agent: {text}")
    # else:
    #     print(f"Agent: {content}")
    #     print(f"Agent: {response["messages"][-1].content}")