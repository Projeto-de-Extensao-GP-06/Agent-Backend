from langchain.tools import tool

@tool
def teste_tool() -> str:
    """Retorna uma string específica para testar funcionamento da tool"""
    return "Teste health check tool"