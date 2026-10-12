from langchain.tools import tool

@tool
def testeTool() -> str:
    """Retorna uma string específica para testar funcionamento da tool"""
    return "Teste health check tool"