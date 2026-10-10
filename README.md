# Agent Backend

Backend em Python para um agente de IA com FastAPI, LangChain e Google Gemini. O projeto recebe mensagens do cliente, pode receber contexto de processo em `dados_processo`, preserva histórico por `session_id` no LangGraph e responde em um formato estruturado para uso em API e diagnósticos.

## Status atual

A aplicação já conta com:
- API FastAPI com rotas de chat
- agente LangChain conectado ao modelo Gemini
- camada de serviço para orquestrar o pipeline
- suporte a `dados_processo` no payload da requisição
- resposta em dois blocos: `resumo_response` e `raw_response`
- limpeza de sessão/thread por `session_id`
- cliente local em `run_local.py` executando o fluxo pela service

## Estrutura do projeto

```text
Agent-Backend/
├── app/
│   └── src/
│       ├── main.py                # inicializa o FastAPI e registra os roteadores
│       ├── agent/
│       │   ├── agent.py           # instancia LLM, memória e compila o agente via grafo
│       │   ├── graph.py           # definição dos nós (agent, tools), arestas e compilação do StateGraph
│       │   ├── graph_state.py     # definição do AgentState (mensagens, dados_processo, llm_calls)
│       │   ├── memory.py          # gerenciamento e limpeza de threads no InMemorySaver
│       │   ├── prompts.py         # prompt do sistema da MarIA e regras de negócio
│       │   └── tools.py           # ferramentas disponíveis para o agente
│       ├── api/
│       │   ├── routes/
│       │   │   └── chat.py        # endpoints da API de chat
│       │   └── schemas/
│       │       └── chat.py        # request/response models da API
│       ├── config/
│       │   └── settings.py        # leitura das variáveis de ambiente com Pydantic
│       └── service/
│           └── agent_service.py   # orquestra a chamada ao agente e o processamento da resposta
├── tests/
│   ├── test_api_structure.py      # valida a estrutura da API
│   ├── test_graph.py              # valida nós, estado e roteamento do grafo LangGraph
│   └── test_service.py            # valida a camada de serviço
├── .env.example                   # exemplo de variáveis de ambiente
├── .gitignore                     # arquivos ignorados pelo Git
├── Dockerfile                     # imagem para executar a API
├── README.md                      # documentação do projeto
├── requirements.txt               # dependências do Python
├── run_local.py                   # cliente local para testar o agente via service
└── .env                           # ambiente local (não versionado)
```

## Responsabilidades dos módulos

### `app/src/main.py`
Cria a instância do FastAPI e inclui o router principal da API.

### `app/src/api/routes/chat.py`
Define os endpoints:
- `POST /api/v1/chat`
- `DELETE /api/v1/chat/{session_id}`

### `app/src/api/schemas/chat.py`
Define os contratos de entrada e saída:
- `message`
- `session_id`
- `dados_processo`
- `resumo_response`
- `raw_response`

### `app/src/service/agent_service.py`
Orquestra o fluxo completo do agente:
1. valida a mensagem
2. normaliza o payload
3. envia `dados_processo` para o agente
4. invoca o grafo com `HumanMessage`
5. extrai o texto final da última mensagem
6. retorna `resposta` e `raw_response`

### `app/src/agent/graph_state.py`
Define o `AgentState` com:
- `messages`: histórico de mensagens gerenciado com o redutor `add_messages`
- `dados_processo`: dados do processo jurídico com redutor para persistência entre turnos
- `llm_calls`: contador de execuções do modelo de linguagem

### `app/src/agent/graph.py`
Monta a arquitetura de grafo do LangGraph (`StateGraph`):
- **Nós**:
  - `agent`: injeta o system prompt e contexto do processo, invocando o modelo com as ferramentas
  - `tools`: executa ferramentas solicitadas através do `ToolNode`
- **Arestas**:
  - `START -> agent`
  - `agent -> conditional_edges`: se o LLM requisitou tools, vai para `tools`; caso contrário, finaliza em `END`
  - `tools -> agent`: retorna a saída da ferramenta para que o modelo formule a resposta final

### `app/src/agent/agent.py`
Configura o cliente Gemini (`ChatGoogleGenerativeAI`), vincula as ferramentas de `tools.py` e compila o grafo com `InMemorySaver`.

### `app/src/agent/memory.py`
Registra threads e remove o histórico persistido daquele `session_id`, limpando a sessão no checkpointer do LangGraph.

### `app/src/agent/tools.py`
Define ferramentas acessíveis ao agente.

### `app/src/agent/prompts.py`
Centraliza o prompt do sistema e as instruções de comportamento do agente.

### `app/src/config/settings.py`
Carrega as variáveis de ambiente do projeto com `pydantic-settings`.

## Requisitos

- Python 3.10+
- chave da API do Google Gemini
- acesso à internet para chamadas ao modelo

## Configuração do ambiente

Crie um arquivo `.env` na raiz do projeto com:

```env
LLM_API_KEY=sua-chave-do-google-gemini
LLM_MODEL=gemini-2.5-flash
```

Observações:
- `LLM_MODEL` deve ser um modelo aceito pelo `ChatGoogleGenerativeAI`
- não versionar chaves reais no repositório

## Instalação

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

No PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Execução local

### Cliente interativo

```bash
python run_local.py
```

Esse cliente envia mensagem por mensagem para a service do agente e é útil para testes manuais sem depender de um frontend.

### API FastAPI

```bash
uvicorn app.main:app --reload
```

A API fica disponível em:

```text
http://127.0.0.1:8000
```

## Endpoints da API

### POST `/api/v1/chat`

Cria ou reutiliza uma conversa por `session_id`.

Payload de exemplo:

```json
{
  "message": "Olá, preciso de ajuda com meu processo",
  "session_id": "sessao-123",
  "dados_processo": {
    "cliente": {
      "nome": "João Pereira",
      "cpf": "123.456.789-09",
      "telefone": "(11) 99999-1234",
      "ativo": true
    },
    "descricaoCaso": "Ação de cobrança referente a contrato de prestação de serviços com atraso de pagamentos.",
    "observacao": "Cliente solicitou revisão do valor cobrado e encaminhamento para mediação.",
    "prioridade": {
      "nome": "Alta",
      "peso": 10
    },
    "faseProcesso": {
      "nome": "Em andamento",
      "ordem": 3
    },
    "ultimaAtualizacao": "2026-08-29T15:30:00",
    "dataHoraInicio": "2026-07-15T09:00:00",
    "ativo": true,
    "dataAudiencia": "2026-09-10T14:00:00",
    "encerradoEm": null,
    "encerradoPorUsuario": null,
    "siglaTribunal": {
      "sigla": "TJSP",
      "nome": "Tribunal de Justiça de São Paulo"
    },
    "valorCausa": 18500.75
  }
}
```

Resposta esperada:

```json
{
  "resumo_response": {
    "response": "Resposta final do assistente",
    "session_id": "sessao-123"
  },
  "raw_response": {
    "messages": [
      "..."
    ],
    "dados_processo": {
      "cliente": {
        "nome": "João Pereira",
        "cpf": "123.456.789-09",
        "telefone": "(11) 99999-1234",
        "ativo": true
      },
      "descricaoCaso": "Ação de cobrança referente a contrato de prestação de serviços com atraso de pagamentos.",
      "observacao": "Cliente solicitou revisão do valor cobrado e encaminhamento para mediação.",
      "prioridade": {
        "nome": "Alta",
        "peso": 10
      },
      "faseProcesso": {
        "nome": "Em andamento",
        "ordem": 3
      },
      "ultimaAtualizacao": "2026-08-29T15:30:00",
      "dataHoraInicio": "2026-07-15T09:00:00",
      "ativo": true,
      "dataAudiencia": "2026-09-10T14:00:00",
      "encerradoEm": null,
      "encerradoPorUsuario": null,
      "siglaTribunal": {
        "sigla": "TJSP",
        "nome": "Tribunal de Justiça de São Paulo"
      },
      "valorCausa": 18500.75
    }
  }
}
```

### DELETE `/api/v1/chat/{session_id}`

Remove a conversa daquele `session_id` do histórico do agente.

Exemplo de resposta:

```json
{
  "message": "Chat excluído com sucesso",
  "session_id": "sessao-123"
}
```

Se a thread não existir, retorna `404`.

## Fluxo atual da aplicação

```text
Cliente / curl / browser
        |
        v
FastAPI
        |
        v
app.api.routes.chat
        |
        v
app.service.agent_service
        |
        v
LangChain + Gemini Agent
        |
        v
Resposta final + raw_response
```

### Etapas do fluxo

1. A requisição chega no endpoint `/api/v1/chat`.
2. O schema valida o payload, incluindo `dados_processo`.
3. O router chama `executarPipelineAgente`.
4. A service normaliza a mensagem, prepara o contexto e envia a conversa ao agente.
5. O agente processa a mensagem com o LangGraph e o `session_id`.
6. A service extrai o texto final e o payload bruto.
7. A API devolve `resumo_response` e `raw_response`.
8. Quando solicitado, o endpoint de exclusão remove a thread do checkpointer do LangGraph.

## Docker

O `Dockerfile` prepara a imagem para rodar a API com Uvicorn. Em produção, é recomendável:
- configurar `LLM_API_KEY` via ambiente ou secret manager
- usar uma imagem Python fixa e testada
- não armazenar segredos no código-fonte

## Observações finais

O projeto já está em um estágio funcional de protótipo e arquitetura base pronta para evolução. A próxima etapa natural é expandir `tools`, `prompts` e a modelagem de domínio para casos reais de negócio, mantendo a estrutura da API e o controle de sessão por `session_id`.
