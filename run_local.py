import asyncio
import json
import sys
from pathlib import Path
from typing import Any

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
from rich.json import JSON
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
- `/debug` : Ativa/desativa o painel completo de debug (pós-anonimização, chamadas, retorno do modelo e pós-desanonimização).
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


def exibir_painel_debug(resultado: dict[str, Any]) -> None:
    """Exibe painel detalhado de debug contendo pós-anonimização, todas as chamadas, retorno do modelo e pós-desanonimização."""
    debug_info = resultado.get("debug_info", {})
    raw_response = resultado.get("raw_response", {})

    console.rule("[bold magenta]PAINEL DE DEBUG DO AGENTE[/bold magenta]")

    # 1. Pós-Anonimização (Dados enviados ao modelo com PII mascarado)
    mensagem_anonimizada = debug_info.get("mensagem_anonimizada")
    mensagem_original = debug_info.get("mensagem_original")
    teve_pii_mensagem = bool(mensagem_anonimizada and mensagem_anonimizada != mensagem_original)

    if teve_pii_mensagem:
        console.print(
            Panel(
                str(mensagem_anonimizada),
                title="[bold cyan]1.1. Pós-Anonimização da Mensagem (PII criptografado via AES)[/bold cyan]",
                border_style="cyan",
            )
        )

    dados_anonimizados = debug_info.get("dados_processo_anonimizado")
    if dados_anonimizados:
        titulo_processo = (
            "[bold cyan]1.2. Pós-Anonimização (dados_processo com PII criptografado via AES)[/bold cyan]"
            if teve_pii_mensagem
            else "[bold cyan]1. Pós-Anonimização (dados_processo com PII criptografado via AES)[/bold cyan]"
        )
        console.print(
            Panel(
                JSON.from_data(dados_anonimizados),
                title=titulo_processo,
                border_style="cyan",
            )
        )
    elif not teve_pii_mensagem:
        console.print(
            Panel(
                "[dim italic]Nenhum dado sensível mascarado e nenhum dado de processo ativo nesta requisição.[/dim italic]",
                title="[bold cyan]1. Pós-Anonimização[/bold cyan]",
                border_style="cyan",
            )
        )

    # 2. Todas as Chamadas (Grafo LangGraph / LLM / Ferramentas)
    mensagens = debug_info.get("mensagens") or raw_response.get("messages", [])
    llm_calls = debug_info.get("llm_calls", raw_response.get("llm_calls", 1))

    chamadas_texto: list[str] = []
    for idx, msg in enumerate(mensagens, start=1):
        tipo = getattr(msg, "type", msg.__class__.__name__)
        conteudo = getattr(msg, "content", "")
        if isinstance(conteudo, list):
            partes = []
            for item in conteudo:
                if isinstance(item, dict) and "text" in item:
                    partes.append(item["text"])
                elif isinstance(item, str):
                    partes.append(item)
            conteudo = " ".join(partes)

        tool_calls = getattr(msg, "tool_calls", None)

        if tipo in ["human", "HumanMessage"]:
            chamadas_texto.append(f"[bold cyan]Chamada #{idx} - Entrada Usuário (HumanMessage):[/bold cyan]\n{conteudo}")
        elif tipo in ["ai", "AIMessage"]:
            bloco = f"[bold green]Chamada #{idx} - Modelo (AIMessage):[/bold green]"
            if tool_calls:
                bloco += "\n[bold yellow]↳ Requisição de Ferramenta(s) (Tool Call):[/bold yellow]"
                for tc in tool_calls:
                    nome_func = tc.get("name", "desconhecida")
                    args = tc.get("args", {})
                    bloco += f"\n  • [bold]{nome_func}[/bold] com argumentos: {json.dumps(args, ensure_ascii=False)}"
            if conteudo:
                bloco += f"\n[white]↳ Conteúdo emitido:[/white] {conteudo}"
            chamadas_texto.append(bloco)
        elif tipo in ["tool", "ToolMessage"]:
            nome_tool = getattr(msg, "name", "Tool")
            chamadas_texto.append(
                f"[bold yellow]Chamada #{idx} - Retorno de Ferramenta (ToolMessage - {nome_tool}):[/bold yellow]\n{conteudo}"
            )
        else:
            chamadas_texto.append(f"[bold white]Chamada #{idx} - {tipo}:[/bold white]\n{conteudo}")

    historico_formatado = "\n\n".join(chamadas_texto) if chamadas_texto else "[dim]Sem histórico registrado.[/dim]"
    console.print(
        Panel(
            historico_formatado,
            title=f"[bold yellow]2. Todas as Chamadas do Grafo (Total de invocações ao LLM: {llm_calls})[/bold yellow]",
            border_style="yellow",
        )
    )

    # 3. Retorno do Modelo (Bruto / Antes da Desanonimização)
    retorno_modelo = debug_info.get("retorno_modelo")
    if not retorno_modelo and mensagens:
        retorno_modelo = getattr(mensagens[-1], "content", "")

    console.print(
        Panel(
            str(retorno_modelo),
            title="[bold red]3. Retorno do Modelo (Bruto / Pré-Desanonimização com Tokens Cifrados)[/bold red]",
            border_style="red",
        )
    )

    # 4. Pós-Desanonimização (Texto Final Restaurado)
    pos_desanonimizacao = debug_info.get("pos_desanonimizacao") or resultado.get("resposta", "")
    console.print(
        Panel(
            str(pos_desanonimizacao),
            title="[bold green]4. Pós-Desanonimização (Texto Final com Dados Reais Restaurados)[/bold green]",
            border_style="green",
        )
    )

    console.rule("[bold magenta]FIM DO DEBUG[/bold magenta]\n")


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

            if isinstance(resultado, dict):
                resposta_texto = resultado.get("resposta", "")
            else:
                resposta_texto = str(resultado)

            console.print("\n[bold green]MarIA:[/bold green]")
            console.print(Markdown(resposta_texto))

            if modo_debug and isinstance(resultado, dict):
                exibir_painel_debug(resultado)

        except Exception as e:
            console.print(f"\n[bold red]Erro ao processar mensagem:[/bold red] {e}")


if __name__ == "__main__":
    asyncio.run(main())
