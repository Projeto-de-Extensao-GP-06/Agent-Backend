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
            self.assertIn("debug_info", resultado)
            self.assertEqual(resultado["debug_info"]["mensagem_original"], "Olá")
            self.assertEqual(resultado["debug_info"]["mensagem_anonimizada"], "Olá")
            self.assertEqual(resultado["debug_info"]["retorno_modelo"], "Olá, posso ajudar!")
            self.assertEqual(resultado["debug_info"]["pos_desanonimizacao"], "Olá, posso ajudar!")

        asyncio.run(_run())

    def test_transformar_mensagem_in(self):
        from src.app.services.agent_service import transformarMensagemIn

        # Mensagem sem PII
        texto_limpo = "Olá, gostaria de saber o status do meu processo."
        self.assertEqual(transformarMensagemIn(texto_limpo), texto_limpo)

        # Mensagem com PII (CPF e telefone)
        texto_sensivel = "Meu CPF é 347.144.900-01 e ligue no 11903030303."
        anonimizado = transformarMensagemIn(texto_sensivel)
        self.assertNotIn("347.144.900-01", anonimizado)
        self.assertNotIn("11903030303", anonimizado)

        # Valores vazios ou não string
        self.assertEqual(transformarMensagemIn(""), "")
        self.assertIsNone(transformarMensagemIn(None))  # type: ignore

    @patch("src.app.services.agent_service.agent")
    def test_executar_pipeline_agente_anonimiza_mensagem_usuario(self, mock_agent):
        from src.app.services.agent_service import executarPipelineAgente

        async def _fake_ainvoke(input_data, config):
            human_msg = input_data["messages"][0].content
            # Verifica se o texto enviado ao modelo já está criptografado (sem CPF explícito)
            self.assertNotIn("347.144.900-01", human_msg)
            # O modelo responde repetindo o que recebeu cifrado
            return {
                "messages": [AIMessage(content=f"Recebi sua solicitação para {human_msg}")],
                "dados_processo": input_data.get("dados_processo"),
                "llm_calls": 1,
            }

        mock_agent.ainvoke = AsyncMock(side_effect=_fake_ainvoke)

        async def _run():
            resultado = await executarPipelineAgente(
                mensagem="Consulta para o CPF 347.144.900-01",
                idSessao="test-pii-sess",
            )
            # Verifica que no resultado final o dado foi desanonimizado com sucesso
            self.assertIn("347.144.900-01", resultado["resposta"])
            self.assertEqual(
                resultado["debug_info"]["mensagem_original"],
                "Consulta para o CPF 347.144.900-01",
            )
            self.assertNotIn(
                "347.144.900-01",
                resultado["debug_info"]["mensagem_anonimizada"],
            )

        asyncio.run(_run())

    @patch("src.app.services.agent_service.agent")
    def test_executar_pipeline_agente_com_mensagem_e_processo_anonimizados(self, mock_agent):
        from src.app.services.agent_service import executarPipelineAgente

        async def _fake_ainvoke(input_data, config):
            human_msg = input_data["messages"][0].content
            processo = input_data["dados_processo"]

            # Mensagem do usuário não pode conter o CPF em texto claro
            self.assertNotIn("347.144.900-01", human_msg)

            # Dicionário do processo não pode conter o CNPJ ou nome da empresa em texto claro
            self.assertNotIn("09.904.401/0001-40", processo["cnpj"])
            self.assertNotIn("Silva & Souza Transportes Ltda", processo["empresa"])

            # Modelo gera resposta mencionando tokens recebidos
            conteudo_resposta = (
                f"Consulta para {human_msg}. "
                f"Empresa: {processo['empresa']} CNPJ: {processo['cnpj']}."
            )
            return {
                "messages": [AIMessage(content=conteudo_resposta)],
                "dados_processo": processo,
                "llm_calls": 1,
            }

        mock_agent.ainvoke = AsyncMock(side_effect=_fake_ainvoke)

        async def _run():
            resultado = await executarPipelineAgente(
                mensagem="Olá, por favor verificar CPF 347.144.900-01",
                idSessao="test-both-sess",
                dadosProcesso={
                    "empresa": "Silva & Souza Transportes Ltda",
                    "cnpj": "09.904.401/0001-40",
                    "valor": 5000.0,
                },
            )

            # O resultado final restaurou todos os dados sensíveis
            resposta = resultado["resposta"]
            self.assertIn("347.144.900-01", resposta)
            self.assertIn("Silva & Souza Transportes Ltda", resposta)
            self.assertIn("09.904.401/0001-40", resposta)

            # Validar debug_info
            self.assertEqual(
                resultado["debug_info"]["mensagem_original"],
                "Olá, por favor verificar CPF 347.144.900-01",
            )
            self.assertNotIn(
                "347.144.900-01",
                resultado["debug_info"]["mensagem_anonimizada"],
            )
            self.assertNotIn(
                "Silva & Souza Transportes Ltda",
                resultado["debug_info"]["dados_processo_anonimizado"]["empresa"],
            )

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

    @patch("src.app.services.agent_service.agent")
    def test_pipeline_reutiliza_placeholder_entre_turnos_e_limpa_ao_excluir_sessao(self, mock_agent):
        from src.app.services.agent_service import excluirSessao, executarPipelineAgente
        from src.app.services.anonymizer import limpar_cofre_sessao

        sessao = "test-multi-turn-vault"
        limpar_cofre_sessao(sessao)

        async def _fake_ainvoke(input_data, config):
            human_msg = input_data["messages"][0].content
            return {
                "messages": [AIMessage(content=f"Confirmado: {human_msg}")],
                "dados_processo": input_data.get("dados_processo"),
                "llm_calls": 1,
            }

        mock_agent.ainvoke = AsyncMock(side_effect=_fake_ainvoke)

        async def _run():
            r1 = await executarPipelineAgente(
                mensagem="Consultar processo",
                idSessao=sessao,
                dadosProcesso={"cpf": "347.144.900-01"},
            )
            placeholder_proc = r1["debug_info"]["dados_processo_anonimizado"]["cpf"]
            self.assertEqual(placeholder_proc, "[CPF_1]")
            self.assertIn("[CPF_1]", r1["debug_info"]["mapa_anonimizacao"])

            # Turno 2 cita o mesmo CPF na mensagem e recebe o mesmo placeholder
            r2 = await executarPipelineAgente(
                mensagem="O CPF é 347.144.900-01",
                idSessao=sessao,
            )
            self.assertIn("[CPF_1]", r2["debug_info"]["mensagem_anonimizada"])
            self.assertIn("347.144.900-01", r2["resposta"])

            from src.app.services.anonymizer import obter_cofre_sessao
            excluirSessao(sessao)
            self.assertEqual(obter_cofre_sessao(sessao).exportar_mapa(), {})

        asyncio.run(_run())
        limpar_cofre_sessao(sessao)


if __name__ == "__main__":
    unittest.main()
