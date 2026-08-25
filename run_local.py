from rich import print
from app.main import agent
from langchain.messages import HumanMessage

while True:
    user_input = input("User: ")
    if user_input.lower() in ["exit", "quit"]:
        print("Exiting the agent.")
        break
    response = agent.invoke({"messages": [HumanMessage(content=user_input)]})
    print(f"Agent: {response["messages"][-1].content}")