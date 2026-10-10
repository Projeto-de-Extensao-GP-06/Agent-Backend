import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage


class ServiceTests(unittest.TestCase):
    @patch("src.app.services.agent_service.agent")
    def test_executar_pipeline_agente_sucesso(self, mock_agent):
        from src.app.services.agent_service import executarPipelineAgente

        mock_agent.ainvoke = AsyncMock(
            return_value={
                "messages": [AIMessage(content="Olá, posso ajudar!")],
                "dados_processo": None,
                "llm_calls": 1,
            }
        )

        async def _run():
            resultado = await executarPipelineAgente(
                mensagem="Olá",
                idSessao="test-sess",
                dadosProcesso={"num": "123"},
            )
            self.assertEqual(resultado["resposta"], "Olá, posso ajudar!")
            self.assertIn("raw_response", resultado)

        asyncio.run(_run())

    def test_executar_pipeline_agente_mensagem_vazia_lanca_erro(self):
        from src.app.services.agent_service import executarPipelineAgente

        async def _run():
            with self.assertRaises(ValueError):
                await executarPipelineAgente(
                    mensagem="   ",
                    idSessao="test-sess",
                )

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
