import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END

from src.app.agent.graph import criarGrafoAgente, montar_mensagens_modelo, should_continue
from src.app.agent.graph_state import AgentState, _atualizar_dados_processo
from src.app.agent.memory import delete_thread
from src.app.agent.tools import testeTool


class GraphTests(unittest.TestCase):
    def test_atualizar_dados_processo_preserva_existente(self):
        antigo = {"numero": "0001234-56.2026.8.26.0100"}
        novo = None
        resultado = _atualizar_dados_processo(antigo, novo)
        self.assertEqual(resultado, antigo)

    def test_atualizar_dados_processo_sobrescreve_com_novo(self):
        antigo = {"numero": "111"}
        novo = {"numero": "222"}
        resultado = _atualizar_dados_processo(antigo, novo)
        self.assertEqual(resultado, novo)

    def test_montar_mensagens_modelo_com_e_sem_processo(self):
        state_sem_processo: AgentState = {
            "messages": [HumanMessage(content="Olá")],
            "dados_processo": None,
        }
        mensagens_1 = montar_mensagens_modelo(state_sem_processo)
        self.assertIsInstance(mensagens_1[0], SystemMessage)
        self.assertEqual(mensagens_1[1].content, "Olá")

        state_com_processo: AgentState = {
            "messages": [HumanMessage(content="Qual o cliente?")],
            "dados_processo": {"cliente": {"nome": "Lucas"}},
        }
        mensagens_2 = montar_mensagens_modelo(state_com_processo)
        self.assertIn("Lucas", mensagens_2[0].content)

    def test_should_continue_sem_tool_calls_retorna_end(self):
        state: AgentState = {
            "messages": [AIMessage(content="Resposta final")],
        }
        self.assertEqual(should_continue(state), END)

    def test_should_continue_com_tool_calls_retorna_tools(self):
        msg = AIMessage(
            content="",
            tool_calls=[{"name": "testeTool", "args": {}, "id": "call_123"}],
        )
        state: AgentState = {
            "messages": [msg],
        }
        self.assertEqual(should_continue(state), "tools")

    def test_fluxo_completo_grafo_com_ferramenta_sincrono(self):
        mock_model = MagicMock()
        mock_bound_model = MagicMock()

        # Primeiro retorno: chamada de ferramenta testeTool
        # Segundo retorno: resposta final com base no resultado da ferramenta
        msg_tool_call = AIMessage(
            content="",
            tool_calls=[{"name": "testeTool", "args": {}, "id": "call_teste_1"}],
        )
        msg_final = AIMessage(content="Ferramenta executada com sucesso: Teste health check tool")

        mock_bound_model.invoke.side_effect = [msg_tool_call, msg_final]
        mock_model.bind_tools.return_value = mock_bound_model

        checkpointer = InMemorySaver()
        grafo = criarGrafoAgente(model=mock_model, tools=[testeTool], checkpointer=checkpointer)

        resultado = grafo.invoke(
            {
                "messages": [HumanMessage(content="Execute o teste")],
                "dados_processo": None,
            },
            config={"configurable": {"thread_id": "test_session_1"}},
        )

        mensagens = resultado["messages"]
        self.assertEqual(len(mensagens), 4)
        self.assertEqual(mensagens[-1].content, "Ferramenta executada com sucesso: Teste health check tool")
        self.assertEqual(resultado.get("llm_calls"), 2)

    def test_fluxo_completo_grafo_assincrono_com_memoria_multi_turnos(self):
        async def _run():
            mock_model = MagicMock()
            mock_bound_model = MagicMock()

            msg_1 = AIMessage(content="Turno 1 respondido")
            msg_2 = AIMessage(content="Turno 2 respondido com base no processo")

            mock_bound_model.ainvoke = AsyncMock(side_effect=[msg_1, msg_2])
            mock_model.bind_tools.return_value = mock_bound_model

            checkpointer = InMemorySaver()
            grafo = criarGrafoAgente(model=mock_model, tools=[testeTool], checkpointer=checkpointer)

            config = {"configurable": {"thread_id": "thread_async_123"}}

            # Turno 1
            res1 = await grafo.ainvoke(
                {
                    "messages": [HumanMessage(content="Pergunta 1")],
                    "dados_processo": {"numero": "999"},
                },
                config=config,
            )
            self.assertEqual(res1["messages"][-1].content, "Turno 1 respondido")
            self.assertEqual(res1["dados_processo"], {"numero": "999"})

            # Turno 2 (sem reenviar dados_processo; deve persistir o anterior)
            res2 = await grafo.ainvoke(
                {
                    "messages": [HumanMessage(content="Pergunta 2")],
                    "dados_processo": None,
                },
                config=config,
            )
            self.assertEqual(res2["messages"][-1].content, "Turno 2 respondido com base no processo")
            self.assertEqual(res2["dados_processo"], {"numero": "999"})
            # Total de mensagens acumuladas: Human1, AI1, Human2, AI2
            self.assertEqual(len(res2["messages"]), 4)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
