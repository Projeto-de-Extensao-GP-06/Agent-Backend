import unittest

from src.app.services.agent_service import (
    transformarDadosProcessoIn,
    transformarDadosProcessoOut,
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


if __name__ == "__main__":
    unittest.main()
