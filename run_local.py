import asyncio
import sys
from pathlib import Path

# Ajusta encoding para UTF-8 no Windows quando suportado
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Garante que a raiz do projeto esteja no sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from src.app.services.agent_service import excluirSessao, executarPipelineAgente

console = Console()

BOAS_VINDAS = """\
**Olá, eu sou a MarIA!** A assistente virtual do **SGPJ** (Sistema Gerenciador de Processos Judiciais).

Posso te ajudar com:
- **Análise de indicadores** da dashboard do sistema;
- **Geração de arquivos ICS** para compromissos na sua agenda;
- **Análise de processos judiciais** e dúvidas do caso.

**Comandos rápidos:**
- `sair` ou `exit` : Encerra a assistente.
- `/limpar` : Limpa o histórico de conversa da sessão atual.
- `/processo` : Alterna o envio de dados de teste de um processo jurídico.
- `/debug` : Ativa/desativa a visualização de metadados do grafo LangGraph.
"""

DADOS_PROCESSO_EXEMPLO = {
    "cliente": {
        "nome": "João Pereira",
        "cpf": "123.456.789-09",
        "telefone": "(11) 99999-1234",
        "ativo": True,
    },
    "descricaoCaso": "Ação de cobrança referente a contrato de prestação de serviços com atraso de pagamentos.",
    "observacao": "Cliente solicitou revisão do valor cobrado e encaminhamento para mediação.",
    "prioridade": {
        "nome": "Alta",
        "peso": 10,
    },
    "faseProcesso": {
        "nome": "Em andamento",
        "ordem": 3,
    },
    "ultimaAtualizacao": "2026-08-29T15:30:00",
    "dataHoraInicio": "2026-07-15T09:00:00",
    "ativo": True,
    "dataAudiencia": "2026-09-10T14:00:00",
    "siglaTribunal": {
        "sigla": "TJSP",
        "nome": "Tribunal de Justiça de São Paulo",
    },
    "valorCausa": 18500.75,
}


async def main():
    id_sessao = "local-session"
    dados_processo_ativo = None
    modo_debug = False

    console.print(
        Panel(
            Markdown(BOAS_VINDAS),
            title="[bold green]MarIA - Assistente SGPJ[/bold green]",
            border_style="green",
        )
    )

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]Você[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Encerrando a assistente. Até logo![/yellow]")
            break

        if not user_input:
            continue

        comando = user_input.lower()
        if comando in ["exit", "quit", "sair"]:
            console.print("[yellow]Encerrando a assistente. Até logo![/yellow]")
            break

        if comando in ["/limpar", "limpar", "clear"]:
            sucesso = excluirSessao(id_sessao)
            if sucesso:
                console.print("[green]Histórico da sessão limpo com sucesso![/green]")
            else:
                console.print("[yellow]Nenhum histórico prévio encontrado para limpar.[/yellow]")
            continue

        if comando in ["/processo", "processo"]:
            if dados_processo_ativo is None:
                dados_processo_ativo = DADOS_PROCESSO_EXEMPLO
                console.print("[green]Dados de processo de exemplo ativados para as mensagens seguintes![/green]")
            else:
                dados_processo_ativo = None
                console.print("[yellow]Dados de processo desativados.[/yellow]")
            continue

        if comando in ["/debug", "debug"]:
            modo_debug = not modo_debug
            status_debug = "ativado" if modo_debug else "desativado"
            console.print(f"[magenta]Modo debug {status_debug}.[/magenta]")
            continue

        try:
            with console.status("[bold green]MarIA pensando...[/bold green]", spinner="dots"):
                resultado = await executarPipelineAgente(
                    mensagem=user_input,
                    idSessao=id_sessao,
                    dadosProcesso=dados_processo_ativo,
                )

            resposta_texto = resultado.get("resposta", "")

            console.print("\n[bold green]MarIA:[/bold green]")
            console.print(Markdown(resposta_texto))

            if modo_debug:
                raw = resultado.get("raw_response", {})
                llm_calls = raw.get("llm_calls", "N/A")
                num_msgs = len(raw.get("messages", []))
                console.print(
                    f"\n[dim magenta][Debug: {llm_calls} chamada(s) ao LLM | {num_msgs} mensagens no histórico do grafo][/dim magenta]"
                )

        except Exception as e:
            console.print(f"\n[bold red]Erro ao processar mensagem:[/bold red] {e}")


if __name__ == "__main__":
    asyncio.run(main())