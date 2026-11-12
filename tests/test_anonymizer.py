import unittest

from src.app.services.agent_service import (
    transformarDadosProcessoIn,
    transformarDadosProcessoOut,
    transformarMensagemIn,
)
from src.app.services.anonymizer import (
    anonimizar_dados_processo,
    anonimizar_texto,
    desanonimizar_texto,
    get_analyzer_engine,
)


class AnonymizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = get_analyzer_engine()

    def test_reconhecedor_cpf(self):
        texto = "Cliente com CPF válido 347.144.900-01 e CPF inválido 347.144.900-00."
        results = self.analyzer.analyze(text=texto, entities=["BR_CPF"], language="pt")
        valores = [texto[r.start : r.end] for r in results]

        self.assertIn("347.144.900-01", valores)
        self.assertNotIn("347.144.900-00", valores)

    def test_reconhecedor_cnpj_tradicional_e_alfanumerico(self):
        texto = (
            "CNPJ tradicional: 09.904.401/0001-40. "
            "CNPJ alfanumérico formatado: E7.ZQS.52V/0001-08. "
            "CNPJ alfanumérico direto: 12ABC34501DE35. "
            "CNPJ inválido descartado: 09.904.401/0001-99."
        )
        results = self.analyzer.analyze(text=texto, entities=["BR_CNPJ"], language="pt")
        valores = [texto[r.start : r.end] for r in results]

        self.assertIn("09.904.401/0001-40", valores)
        self.assertIn("E7.ZQS.52V/0001-08", valores)
        self.assertIn("12ABC34501DE35", valores)
        self.assertNotIn("09.904.401/0001-99", valores)

    def test_reconhecedor_rg(self):
        texto = "Documento RG 12.345.678-9 e identidade 98.765.432-X da SSP/SP."
        results = self.analyzer.analyze(text=texto, entities=["BR_RG"], language="pt")
        valores = [texto[r.start : r.end] for r in results]

        self.assertIn("12.345.678-9", valores)
        self.assertIn("98.765.432-X", valores)

    def test_reconhecedor_telefone_celular_e_fixo(self):
        texto = (
            "Celular formatado (11) 90303-0303 e direto 11903030303. "
            "Fixo formatado (11) 0303-0303 e fixo direto 1103030303."
        )
        results = self.analyzer.analyze(text=texto, entities=["PHONE_NUMBER"], language="pt")
        valores = [texto[r.start : r.end] for r in results]

        self.assertIn("(11) 90303-0303", valores)
        self.assertIn("11903030303", valores)
        self.assertIn("(11) 0303-0303", valores)
        self.assertIn("1103030303", valores)

    def test_reconhecedor_razao_social(self):
        texto = "Contrato com Silva & Souza Transportes Ltda e a empresa Acme Soluções Digitais S.A."
        results = self.analyzer.analyze(text=texto, entities=["BR_RAZAO_SOCIAL"], language="pt")
        valores = [texto[r.start : r.end] for r in results]

        self.assertIn("Silva & Souza Transportes Ltda", valores)
        self.assertIn("Acme Soluções Digitais S.A.", valores)

    def test_reconhecedor_cnj(self):
        texto = (
            "Processo judicial nº 0000001-84.2020.8.26.0001 em andamento. "
            "Número inválido: 0000001-00.2020.8.26.0001."
        )
        results = self.analyzer.analyze(text=texto, entities=["BR_CNJ"], language="pt")
        valores = [texto[r.start : r.end] for r in results]

        self.assertIn("0000001-84.2020.8.26.0001", valores)
        self.assertNotIn("0000001-00.2020.8.26.0001", valores)

    def test_anonimizacao_reversivel_e_desanonimizacao_texto(self):
        original = "O cliente John Doe tem o CPF 347.144.900-01 e telefone (11) 90303-0303."
        anonimizado, itens = anonimizar_texto(original)

        self.assertNotEqual(original, anonimizado)
        self.assertNotIn("347.144.900-01", anonimizado)
        self.assertNotIn("(11) 90303-0303", anonimizado)

        restaurado = desanonimizar_texto(anonimizado)
        self.assertEqual(original, restaurado)

    def test_anonimizar_dados_processo_dicionario(self):
        dados_processo = {
            "cliente": {
                "nome": "John Doe",
                "cpf": "347.144.900-01",
                "telefone": "(11) 90303-0303",
            },
            "descricaoCaso": "Ação contra Silva & Souza Transportes Ltda, CNPJ 09.904.401/0001-40.",
            "processo_cnj": "0000001-84.2020.8.26.0001",
            "valorCausa": 15000.50,
            "ativo": True,
        }

        anonimizado = anonimizar_dados_processo(dados_processo)

        self.assertIsNotNone(anonimizado)
        self.assertEqual(anonimizado["valorCausa"], 15000.50)
        self.assertEqual(anonimizado["ativo"], True)

        self.assertNotIn("John Doe", anonimizado["cliente"]["nome"])
        self.assertNotIn("347.144.900-01", anonimizado["cliente"]["cpf"])
        self.assertNotIn("(11) 90303-0303", anonimizado["cliente"]["telefone"])
        self.assertNotIn("09.904.401/0001-40", anonimizado["descricaoCaso"])
        self.assertNotIn("0000001-84.2020.8.26.0001", anonimizado["processo_cnj"])

        # Testa restauração de campo do processo
        self.assertEqual(
            desanonimizar_texto(anonimizado["cliente"]["cpf"]),
            "347.144.900-01",
        )
        self.assertEqual(
            desanonimizar_texto(anonimizado["processo_cnj"]),
            "0000001-84.2020.8.26.0001",
        )

    def test_schema_sgpj_anonimiza_apenas_campos_sensiveis_e_preserva_metadados(self):
        dados_sgpj = {
            "usuarioResponsavelId": "usr-101",
            "usuarioResponsavelNome": "Dra. Fernanda Lima",
            "clienteId": "cli-502",
            "clientNomeRazaoSocial": "João Pereira",
            "descricaoCaso": "Ação de indenização de João Pereira fundada na LGPD contra Silva & Souza Transportes Ltda.",
            "obervacao": "Cliente João Pereira solicitou acompanhamento prioritário no SAJ.",
            "valorCausa": 25000.00,
            "prioridade": {"nome": "Alta", "peso": 10},
            "faseProcesso": {"nome": "Em andamento", "ordem": 3},
            "status": "Ativo",
            "dataAudiencia": "2026-09-10T14:00:00",
            "dataHoraInicio": "2026-07-15T09:00:00",
            "ultimaAtualizacao": "2026-08-29T15:30:00",
            "siglaTribunal": {"sigla": "TJSP", "nome": "Tribunal de Justiça de São Paulo"},
            "numeroCnj": "0000001-84.2020.8.26.0001",
            "tribunalTramitacao": "Tribunal de Justiça de São Paulo",
            "instancia": "1ª Instância",
            "dataAjuizamento": "2020-01-10",
            "nivelSigilo": "Público",
            "classeProcessual": "Procedimento Comum Cível",
            "formato": "Eletrônico",
            "sistemaTribunal": "SAJ",
            "orgaoJulgador": "1ª Vara Cível",
            "assunto": "Proteção de Dados Pessoais (LGPD)",
            "ultimoMovimento": "Despacho proferido intimando Dra. Fernanda Lima no processo 0000001-84.2020.8.26.0001.",
            "historicoProcessoResponses": [
                {
                    "usuarioResponsavelId": "usr-101",
                    "usuarioResponsavelNome": "Dra. Fernanda Lima",
                    "dataAlteracao": "2026-08-29T15:30:00",
                    "tipoAtualizacao": "ALTERACAO_FASE",
                }
            ],
        }

        mapa_tokens: dict[str, str] = {}
        anonimizado = transformarDadosProcessoIn(dados_sgpj, mapaTokens=mapa_tokens)

        # 1. Identificação, Partes e CNJ foram cifrados
        self.assertNotEqual(anonimizado["usuarioResponsavelId"], "usr-101")
        self.assertNotEqual(anonimizado["usuarioResponsavelNome"], "Dra. Fernanda Lima")
        self.assertNotEqual(anonimizado["clienteId"], "cli-502")
        self.assertNotEqual(anonimizado["clientNomeRazaoSocial"], "João Pereira")
        self.assertNotEqual(anonimizado["numeroCnj"], "0000001-84.2020.8.26.0001")

        # 2. Histórico: quem alterou foi cifrado, quando e tipo foram preservados
        hist = anonimizado["historicoProcessoResponses"][0]
        self.assertEqual(hist["usuarioResponsavelId"], anonimizado["usuarioResponsavelId"])
        self.assertEqual(hist["usuarioResponsavelNome"], anonimizado["usuarioResponsavelNome"])
        self.assertEqual(hist["dataAlteracao"], "2026-08-29T15:30:00")
        self.assertEqual(hist["tipoAtualizacao"], "ALTERACAO_FASE")

        # 3. Textos livres tiveram PII e nomes das partes cifrados, mas preservaram LGPD e SAJ
        self.assertNotIn("João Pereira", anonimizado["descricaoCaso"])
        self.assertNotIn("Silva & Souza Transportes Ltda", anonimizado["descricaoCaso"])
        self.assertIn("LGPD", anonimizado["descricaoCaso"])

        self.assertNotIn("João Pereira", anonimizado["obervacao"])
        self.assertIn("SAJ", anonimizado["obervacao"])

        self.assertNotIn("Dra. Fernanda Lima", anonimizado["ultimoMovimento"])
        self.assertNotIn("0000001-84.2020.8.26.0001", anonimizado["ultimoMovimento"])

        # 4. Metadados do sistema e do tribunal permaneceram 100% em texto claro
        self.assertEqual(anonimizado["valorCausa"], 25000.00)
        self.assertEqual(anonimizado["prioridade"], {"nome": "Alta", "peso": 10})
        self.assertEqual(anonimizado["faseProcesso"], {"nome": "Em andamento", "ordem": 3})
        self.assertEqual(anonimizado["status"], "Ativo")
        self.assertEqual(anonimizado["siglaTribunal"], {"sigla": "TJSP", "nome": "Tribunal de Justiça de São Paulo"})
        self.assertEqual(anonimizado["tribunalTramitacao"], "Tribunal de Justiça de São Paulo")
        self.assertEqual(anonimizado["instancia"], "1ª Instância")
        self.assertEqual(anonimizado["nivelSigilo"], "Público")
        self.assertEqual(anonimizado["classeProcessual"], "Procedimento Comum Cível")
        self.assertEqual(anonimizado["formato"], "Eletrônico")
        self.assertEqual(anonimizado["sistemaTribunal"], "SAJ")
        self.assertEqual(anonimizado["orgaoJulgador"], "1ª Vara Cível")
        self.assertEqual(anonimizado["assunto"], "Proteção de Dados Pessoais (LGPD)")

        # 5. Mensagem do usuário mencionando LGPD, TJSP e o nome real do cliente (João Pereira)
        msg_usuario = "Como a lgpd se aplica ao processo do João Pereira no TJSP?"
        msg_anonimizada = transformarMensagemIn(
            msg_usuario,
            dadosProcesso=dados_sgpj,
            mapaTokens=mapa_tokens,
        )
        self.assertIn("lgpd", msg_anonimizada)
        self.assertIn("TJSP", msg_anonimizada)
        self.assertNotIn("João Pereira", msg_anonimizada)
        self.assertIn(anonimizado["clientNomeRazaoSocial"], msg_anonimizada)

        # 6. Desanonimização restaura perfeitamente
        self.assertEqual(transformarDadosProcessoOut(msg_anonimizada), msg_usuario)

    def test_transformar_dados_processo_in_e_out(self):
        dados_processo = {
            "cpf": "347.144.900-01",
            "empresa": "Silva & Souza Transportes Ltda",
        }

        # 1. Entrada (transformarDadosProcessoIn)
        processo_anonimizado = transformarDadosProcessoIn(dados_processo)
        self.assertNotEqual(processo_anonimizado["cpf"], "347.144.900-01")

        # 2. Resposta simulada do LLM citando o token cifrado
        token_cpf = processo_anonimizado["cpf"]
        mensagem_llm = f"O processo referente ao CPF {token_cpf} foi deferido com sucesso."

        # 3. Saída (transformarDadosProcessoOut)
        resposta_final = transformarDadosProcessoOut(mensagem_llm)
        self.assertEqual(
            resposta_final,
            "O processo referente ao CPF 347.144.900-01 foi deferido com sucesso.",
        )

    def test_transformar_mensagem_in_e_dados_processo_combinados(self):
        mensagem_usuario = "Meu CPF é 347.144.900-01 e telefone (11) 90303-0303."
        dados_processo = {
            "reclamado": "Silva & Souza Transportes Ltda",
            "processo": "0000001-84.2020.8.26.0001",
        }

        msg_anonimizada = transformarMensagemIn(mensagem_usuario, dadosProcesso=dados_processo)
        proc_anonimizado = transformarDadosProcessoIn(dados_processo)

        # Mensagem do usuário foi devidamente anonimizada
        self.assertNotIn("347.144.900-01", msg_anonimizada)
        self.assertNotIn("(11) 90303-0303", msg_anonimizada)

        # Dicionário do processo foi devidamente anonimizado
        self.assertNotIn("Silva & Souza Transportes Ltda", proc_anonimizado["reclamado"])
        self.assertNotIn("0000001-84.2020.8.26.0001", proc_anonimizado["processo"])

        # LLM responde citando os tokens cifrados de ambos
        resposta_simulada = (
            f"Confirmado para o titular do documento e telefone. "
            f"Processo {proc_anonimizado['processo']} contra {proc_anonimizado['reclamado']}."
        )
        resposta_restaurada = transformarDadosProcessoOut(resposta_simulada)

        self.assertIn("0000001-84.2020.8.26.0001", resposta_restaurada)
        self.assertIn("Silva & Souza Transportes Ltda", resposta_restaurada)

    def test_nao_censura_siglas_juridicas_lgpd_nem_comandos_do_usuario(self):
        frases = [
            "O que a lgpd diz sobre este processo?",
            "Como a lgpd me afeta e o que ela me garante?",
            "Explique as regras da LGPD e do CNJ no sistema SAJ do TJSP.",
            "Retorne os dados do processo.",
            "Retorne por favor.",
            "Retorne.",
            "Faça a consulta do processo.",
            "Envie o relatório por email.",
            "Busque as informações.",
            "Atualize o status da causa.",
            "Cancele a audiência.",
            "Quero saber o andamento.",
        ]

        for frase in frases:
            anonimizado, itens = anonimizar_texto(frase)
            self.assertEqual(
                anonimizado,
                frase,
                f"A frase '{frase}' teve termos criptografados indevidamente: {anonimizado}",
            )
            self.assertEqual(len(itens), 0)

        # Garante que com PII na mesma frase, o comando e siglas são preservados e o PII é cifrado
        frase_mista = "Retorne os dados de LGPD do CPF 347.144.900-01, por favor."
        anonimizado_misto, _ = anonimizar_texto(frase_mista)
        self.assertTrue(anonimizado_misto.startswith("Retorne os dados de LGPD do CPF "))
        self.assertNotIn("347.144.900-01", anonimizado_misto)
        self.assertTrue(anonimizado_misto.endswith(", por favor."))


if __name__ == "__main__":
    unittest.main()
