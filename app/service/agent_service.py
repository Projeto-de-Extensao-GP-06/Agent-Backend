from collections.abc import Mapping, Sequence
from typing import Any

from langchain.messages import HumanMessage

from app.agent.agent import criar_agente

agent = criar_agente()

def _conteudo_para_texto(conteudo: Any) -> str:
	if isinstance(conteudo, str):
		return conteudo.strip()

	if isinstance(conteudo, Sequence) and not isinstance(conteudo, (str, bytes)):
		partes: list[str] = []
		for item in conteudo:
			if isinstance(item, Mapping):
				texto = item.get("text")
				if isinstance(texto, str):
					partes.append(texto)
			elif isinstance(item, str):
				partes.append(item)
		return "".join(partes).strip()

	return ""


async def executar_pipeline_agente(mensagem: str, id_sessao: str) -> str:
	mensagem_normalizada = mensagem.strip()
	if not mensagem_normalizada:
		raise ValueError("A mensagem nao pode estar vazia")

	resultado = await agent.ainvoke(
		{"messages": [HumanMessage(content=mensagem_normalizada)]},
		{"configurable": {"thread_id": id_sessao}},
	)

	mensagens = resultado.get("messages", [])
	if not mensagens:
		raise RuntimeError("O assistente nao retornou uma resposta")

	resposta = _conteudo_para_texto(mensagens[-1].content)
	if not resposta:
		raise RuntimeError("O assistente retornou uma resposta sem texto")

	return resposta