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

        msg_anonimizada = transformarMensagemIn(mensagem_usuario)
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

    def test_deny_list_ignora_verbos_e_comandos_no_inicio_de_frase(self):
        # Garante que 'Retorne' e outros comandos usuais NÃO sejam criptografados
        frases_comandos = [
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

        for frase in frases_comandos:
            anonimizado, itens = anonimizar_texto(frase)
            self.assertEqual(
                anonimizado,
                frase,
                f"A frase '{frase}' teve termos criptografados indevidamente: {anonimizado}",
            )
            self.assertEqual(len(itens), 0)

        # Garante que com PII na mesma frase, o comando é preservado e o PII é cifrado
        frase_mista = "Retorne os dados do CPF 347.144.900-01, por favor."
        anonimizado_misto, _ = anonimizar_texto(frase_mista)
        self.assertTrue(anonimizado_misto.startswith("Retorne os dados do CPF "))
        self.assertNotIn("347.144.900-01", anonimizado_misto)
        self.assertTrue(anonimizado_misto.endswith(", por favor."))

    def test_placeholders_curtos_e_reutilizacao_na_mesma_sessao(self):
        from src.app.services.anonymizer import (
            PLACEHOLDER_PATTERN,
            limpar_cofre_sessao,
            obter_cofre_sessao,
        )

        sessao = "sessao-historico-teste"
        limpar_cofre_sessao(sessao)

        historico = {
            "alteracoes": [
                {"responsavel": "John Doe", "descricao": "Processo criado."},
                {"responsavel": "Jane Smith", "descricao": "Observações atualizadas."},
                {"responsavel": "John Doe", "descricao": "Adiciona valor da causa."},
            ]
        }

        anonimizado = anonimizar_dados_processo(historico, session_id=sessao)
        r0 = anonimizado["alteracoes"][0]["responsavel"]
        r1 = anonimizado["alteracoes"][1]["responsavel"]
        r2 = anonimizado["alteracoes"][2]["responsavel"]

        self.assertRegex(r0, PLACEHOLDER_PATTERN)
        self.assertRegex(r1, PLACEHOLDER_PATTERN)
        # Mesmo responsável recebe o mesmo placeholder curto; diferente recebe outro
        self.assertEqual(r0, r2)
        self.assertNotEqual(r0, r1)

        # Cofre armazena apenas valores cifrados em AES, nunca texto claro
        mapa = obter_cofre_sessao(sessao).exportar_mapa()
        self.assertIn(r0, mapa)
        self.assertNotEqual(mapa[r0], "John Doe")
        self.assertNotIn("John Doe", str(mapa))

        resposta_llm = f"Alterações de {r0} e {r1}, finalizadas por {r2}."
        restaurado = desanonimizar_texto(resposta_llm, session_id=sessao)
        self.assertEqual(
            restaurado,
            "Alterações de John Doe e Jane Smith, finalizadas por John Doe.",
        )

        self.assertTrue(limpar_cofre_sessao(sessao))
        # Após limpar o cofre, placeholders não são mais restaurados
        self.assertEqual(desanonimizar_texto(r0, session_id=sessao), r0)

    def test_isolamento_entre_sessoes_e_fallback_aes_direto(self):
        from presidio_anonymizer.operators.aes_cipher import AESCipher
        from src.app.config.settings import settings
        from src.app.services.anonymizer import limpar_cofre_sessao

        s1, s2 = "sessao-iso-1", "sessao-iso-2"
        limpar_cofre_sessao(s1)
        limpar_cofre_sessao(s2)

        t1, _ = anonimizar_texto("CPF 347.144.900-01", session_id=s1)
        t2, _ = anonimizar_texto("CPF 529.982.247-25", session_id=s2)

        # Ambas iniciam em [CPF_1], mas cada sessão restaura apenas o próprio dado
        self.assertEqual(t1, "CPF [CPF_1]")
        self.assertEqual(t2, "CPF [CPF_1]")
        self.assertEqual(desanonimizar_texto(t1, session_id=s1), "CPF 347.144.900-01")
        self.assertEqual(desanonimizar_texto(t2, session_id=s2), "CPF 529.982.247-25")

        # Fallback legado: token AES direto (inclusive envolvido em _..._ Markdown)
        aes_direto = AESCipher.encrypt(settings.anonymization_key.encode("utf-8"), "347.144.900-01")
        self.assertEqual(desanonimizar_texto(f"CPF _{aes_direto}_", session_id=s1), "CPF _347.144.900-01_")

        limpar_cofre_sessao(s1)
        limpar_cofre_sessao(s2)


if __name__ == "__main__":
    unittest.main()
