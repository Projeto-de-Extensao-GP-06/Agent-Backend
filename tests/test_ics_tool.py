import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.app.agent.graph import montar_mensagens_modelo
from src.app.agent.tools import compilar_anexo_ics, gerarEventoIcs
from src.app.schemas.chat import ChatRequest, ChatResponse
from src.app.services.anonymizer import anonimizar_texto


class IcsToolTests(unittest.TestCase):
    def test_validacao_exige_hora_fim_quando_nao_dia_inteiro(self):
        msg = gerarEventoIcs.invoke(
            {
                "titulo": "Audiência de Conciliação",
                "data_inicio": "2026-11-20",
                "dia_inteiro": False,
                "hora_inicio": "14:00",
                "hora_fim": None,
            }
        )
        self.assertIn("Erro de validação", msg)

    def test_validacao_rejeita_hora_fim_anterior_ou_igual_ao_inicio(self):
        msg = gerarEventoIcs.invoke(
            {
                "titulo": "Reunião com Cliente",
                "data_inicio": "2026-11-20",
                "dia_inteiro": False,
                "hora_inicio": "14:00",
                "hora_fim": "14:00",
            }
        )
        self.assertIn("Erro de validação", msg)

    def test_validacao_rejeita_lembrete_invalido_e_data_inexistente(self):
        msg_data = gerarEventoIcs.invoke(
            {
                "titulo": "Prazo",
                "data_inicio": "2026-02-30",
                "dia_inteiro": True,
            }
        )
        self.assertIn("Erro de validação", msg_data)

        msg_lembrete = gerarEventoIcs.invoke(
            {
                "titulo": "Prazo",
                "data_inicio": "2026-11-20",
                "dia_inteiro": True,
                "lembrete": "15m",
            }
        )
        self.assertIn("Erro de validação", msg_lembrete)

    def test_geracao_evento_com_horario_e_alarme_rfc5545(self):
        tool_msg = gerarEventoIcs.invoke(
            {
                "name": "gerarEventoIcs",
                "args": {
                    "titulo": "Audiência de Instrução",
                    "data_inicio": "2026-11-20",
                    "dia_inteiro": False,
                    "hora_inicio": "14:30",
                    "hora_fim": "15:30",
                    "descricao": "Levar procuração\nChegar 15 min antes",
                    "local": "2ª Vara, Fórum Central; Sala 10",
                    "lembrete": "-PT15M",
                },
                "id": "call_ics_1",
                "type": "tool_call",
            }
        )
        self.assertIsInstance(tool_msg, ToolMessage)
        self.assertIsNotNone(tool_msg.artifact)

        anexo = compilar_anexo_ics(tool_msg.artifact)
        self.assertEqual(anexo["filename"], "audiencia-de-instrucao-2026-11-20.ics")
        self.assertEqual(anexo["title"], "Audiência de Instrução")
        self.assertEqual(anexo["mime_type"], "text/calendar;charset=utf-8")

        ics = anexo["content"]
        self.assertIn("\r\n", ics)
        self.assertIn("PRODID:-//SGPJ//Sistema Gerenciador de Processos Judiciais//PT-BR", ics)
        self.assertIn("DTSTART:20261120T143000", ics)
        self.assertIn("DTEND:20261120T153000", ics)
        self.assertIn(r"DESCRIPTION:Levar procuração\nChegar 15 min antes", ics)
        self.assertIn(r"LOCATION:2ª Vara\, Fórum Central\; Sala 10", ics)
        self.assertIn("BEGIN:VALARM", ics)
        self.assertIn("TRIGGER:-PT15M", ics)
        self.assertIn("END:VALARM", ics)

    def test_geracao_evento_dia_inteiro_dtend_exclusivo(self):
        tool_msg = gerarEventoIcs.invoke(
            {
                "name": "gerarEventoIcs",
                "args": {
                    "titulo": "Prazo Recursal",
                    "data_inicio": "2026-11-20",
                    "dia_inteiro": True,
                },
                "id": "call_ics_2",
                "type": "tool_call",
            }
        )
        anexo = compilar_anexo_ics(tool_msg.artifact)
        ics = anexo["content"]
        self.assertIn("DTSTART;VALUE=DATE:20261120", ics)
        self.assertIn("DTEND;VALUE=DATE:20261121", ics)
        self.assertNotIn("BEGIN:VALARM", ics)

    def test_desanonimizacao_no_ics_sem_vazar_pii_para_llm(self):
        nome_real = "Empresa Alfa, Ltda; Filial"
        token_cifrado, _ = anonimizar_texto(
            f"Audiência de {nome_real}",
            termos_conhecidos=[nome_real],
        )

        tool_msg = gerarEventoIcs.invoke(
            {
                "name": "gerarEventoIcs",
                "args": {
                    "titulo": token_cifrado,
                    "data_inicio": "2026-11-25",
                    "dia_inteiro": False,
                    "hora_inicio": "10:00",
                    "hora_fim": "11:00",
                },
                "id": "call_ics_pii",
                "type": "tool_call",
            }
        )

        # Conteúdo devolvido ao modelo não pode conter o nome real descriptografado
        self.assertNotIn(nome_real, tool_msg.content)

        # Arquivo .ics final para o usuário deve conter o valor restaurado e escapado
        anexo = compilar_anexo_ics(tool_msg.artifact)
        self.assertEqual(anexo["title"], f"Audiência de {nome_real}")
        self.assertIn(r"SUMMARY:Audiência de Empresa Alfa\, Ltda\; Filial", anexo["content"])
        self.assertEqual(anexo["filename"], "audiencia-de-empresa-alfa-ltda-filial-2026-11-25.ics")

    def test_montar_mensagens_injeta_referencia_temporal_com_fallback(self):
        mensagens = montar_mensagens_modelo(
            {
                "messages": [HumanMessage(content="Gere evento amanhã")],
                "timezone": "Timezone/Invalido",
            }
        )
        self.assertIsInstance(mensagens[0], SystemMessage)
        self.assertIn("DATA E HORA ATUAL DE REFERÊNCIA", mensagens[0].content)
        self.assertIn("America/Sao_Paulo", mensagens[0].content)
        self.assertIn("gerarEventoIcs", mensagens[0].content)

    @patch("src.app.services.agent_service.agent")
    def test_pipeline_retorna_apenas_anexos_do_turno_atual(self, mock_agent):
        from src.app.services.agent_service import executarPipelineAgente

        anexo_antigo = ToolMessage(
            content="ok antigo",
            tool_call_id="call_old",
            artifact={
                "titulo": "Evento Antigo",
                "data_inicio": "2026-11-10",
                "data_termino": "2026-11-10",
                "dia_inteiro": True,
                "hora_inicio": None,
                "hora_fim": None,
                "descricao": None,
                "local": None,
                "lembrete": None,
            },
        )
        anexo_atual = ToolMessage(
            content="ok atual",
            tool_call_id="call_new",
            artifact={
                "titulo": "Evento Atual",
                "data_inicio": "2026-11-20",
                "data_termino": "2026-11-20",
                "dia_inteiro": False,
                "hora_inicio": "09:00",
                "hora_fim": "10:00",
                "descricao": None,
                "local": None,
                "lembrete": "-PT30M",
            },
        )

        mock_agent.ainvoke = AsyncMock(
            return_value={
                "messages": [
                    HumanMessage(content="Turno 1"),
                    anexo_antigo,
                    AIMessage(content="Gerado turno 1"),
                    HumanMessage(content="Turno 2"),
                    anexo_atual,
                    AIMessage(content="Gerado turno 2"),
                ],
                "llm_calls": 2,
            }
        )

        async def _run():
            res = await executarPipelineAgente(
                mensagem="Turno 2",
                idSessao="sessao-ics-teste",
                timezone="America/Sao_Paulo",
            )
            self.assertEqual(len(res["attachments"]), 1)
            self.assertEqual(res["attachments"][0]["title"], "Evento Atual")
            self.assertEqual(res["attachments"][0]["filename"], "evento-atual-2026-11-20.ics")

        asyncio.run(_run())

    def test_schemas_chat_suportam_timezone_e_attachments(self):
        req = ChatRequest(message="Olá", timezone="America/Sao_Paulo")
        self.assertEqual(req.timezone, "America/Sao_Paulo")

        resp = ChatResponse(
            resumo_response={
                "response": "Evento gerado.",
                "session_id": "abc",
                "attachments": [
                    {
                        "filename": "audiencia-2026-11-20.ics",
                        "title": "Audiência",
                        "content": "BEGIN:VCALENDAR\r\nEND:VCALENDAR",
                    }
                ],
            }
        )
        self.assertEqual(len(resp.resumo_response.attachments), 1)
        self.assertEqual(resp.resumo_response.attachments[0].mime_type, "text/calendar;charset=utf-8")


if __name__ == "__main__":
    unittest.main()
