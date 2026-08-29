# Agent Backend

Backend para uma aplicacao baseada em agente de IA, com integracao ao Google Gemini por meio do LangChain e uma API HTTP planejada com FastAPI.

## Status atual

O agente, o fluxo de teste local pelo terminal e a API FastAPI estao configurados. O endpoint de chat usa sessoes para preservar o contexto de cada conversa. Os modulos de tools, memory e prompts tambem estao reservados para implementacao.

## Estrutura do projeto

```text
Agent-Backend/
├── app/
│   ├── main.py                 # Instancia o FastAPI e registra os roteadores
│   ├── agent/
│   │   ├── agent.py            # Configura o modelo e cria o agente LangChain
│   │   ├── memory.py           # Memoria e contexto das conversas (planejado)
│   │   ├── prompts.py          # Prompts e instrucoes do agente (planejado)
│   │   └── tools.py            # Tools disponiveis para o agente (planejado)
│   ├── api/
│   │   └── chat_router.py      # Endpoint HTTP de chat
│   ├── config/
│   │   └── settings.py         # Le e valida as variaveis de ambiente
│   └── service/
│       └── agent_service.py    # Pre e pos-processamento das requisicoes
├── .env.example                # Exemplo de configuracao local
├── .gitignore                  # Arquivos ignorados pelo Git
├── Dockerfile                  # Imagem para executar o backend
├── requirements.txt            # Dependencias Python
└── run_local.py                # Cliente interativo para teste local
```

## Responsabilidades

### `app/main.py`

Cria a instancia do FastAPI e registra os endpoints da aplicacao.

### `app/agent/agent.py`

Cria o `ChatGoogleGenerativeAI` usando o modelo e a chave definidos no ambiente. Em seguida, entrega esse modelo ao `create_agent` do LangChain. As tools e o prompt do agente serao conectados aqui quando forem implementados.

### `app/config/settings.py`

Define as configuracoes obrigatorias da aplicacao: `llm_api_key`, a chave de acesso ao Google Gemini, e `llm_model`, o identificador do modelo utilizado. As configuracoes sao carregadas do arquivo `.env` com `pydantic-settings`.

### `app/service/agent_service.py`

Orquestra o ciclo de uma requisicao, invoca o agente com a sessao recebida e extrai a resposta textual para a API.

### `app/agent/tools.py`

Modulo reservado para as ferramentas que o agente podera escolher e executar. Cada tool devera ter uma responsabilidade bem definida e validar suas entradas e saidas.

### `app/agent/memory.py`

Modulo reservado para gerenciar o historico e o contexto das conversas, incluindo a estrategia de persistencia que for escolhida.

### `app/agent/prompts.py`

Modulo reservado para centralizar o prompt de sistema, instrucoes, regras de comportamento e demais mensagens usadas pelo agente.

## Requisitos

- Python 3.10 ou superior.
- Uma chave de API do Google Gemini.
- Acesso a internet para as chamadas ao modelo.

## Execucao local

### 1. Criar o ambiente virtual

Na raiz do projeto:

```powershell
python -m venv venv
```

Ative no Windows PowerShell:

```powershell
venv\Scripts\Activate.ps1
```

Ou no Git Bash:

```bash
source venv/Scripts/activate
```

### 2. Instalar as dependencias

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configurar o ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
LLM_API_KEY=sua-chave-do-google-gemini
LLM_MODEL=modelo-desejado
```

`LLM_MODEL` deve conter apenas o identificador aceito pelo `ChatGoogleGenerativeAI`, sem prefixos como `google_genai:`. Nunca versionar uma chave real no repositorio.

### 4. Executar localmente

```powershell
python run_local.py
```

Digite uma mensagem no prompt `User:`. Para encerrar, use `exit` ou `quit`. O cliente envia a entrada no formato de mensagens esperado pelo agente LangChain e imprime o conteudo da ultima mensagem retornada.

## Execucao da API

O ponto de entrada da API e `app.main:app`. Inicie a aplicacao com:

```powershell
uvicorn app.main:app --reload
```

Envie mensagens para `POST /api/v1/chat`:

    {
      "message": "Qual e o status do processo?",
      "session_id": "opcional-para-manter-o-contexto"
    }

A resposta inclui o texto do assistente e o `session_id` a ser reutilizado nas proximas mensagens.

## Modelos disponíveis

| Modelo | Requisições por minuto | Pico de tokens por minuto | Requisições por dia
-| - | - | - |
gemini-3.5-Flash-lite | 15 | 250K | 500
gemini-3.1-pro | 15 | 250K | 500
gemini-2-flash | 5 | 250K | 20
gemini-2.5-flash-lite | 10 | 250K | 20
gemini-2.5-pro | 5 | 250K | 20
gemini-3.5-flash | 5 | 250K | 20
gemini-3.6-flash | 5 | 250K | 20
gemini3.7-flash | 5 | 250K | 20

## Fluxo da aplicacao

```text
Cliente
	|
	v
FastAPI: recebe a requisicao
	|
	v
Agent Service: pre-tratamento, validacao e normalizacao
	|
	v
Agente de IA: interpreta a requisicao e decide se deve usar uma tool
	|
	+--> Tool: executa uma operacao externa, quando necessario
	|
	v
Agent Service: formatacao da resposta, guardrails e pos-tratamento
	|
	v
FastAPI: retorna a resposta ao cliente
```

### Etapas

1. A requisicao chega por um endpoint da FastAPI.
2. O `agent_service` faz o pre-tratamento, valida os dados e prepara o contexto.
3. O agente recebe a mensagem e o contexto. A IA decide responder diretamente ou chamar uma tool.
4. Quando uma tool e chamada, seu resultado retorna ao agente para compor a resposta final.
5. O `agent_service` aplica formatacao, guardrails, validacoes e demais regras de pos-processamento.
6. A FastAPI devolve ao cliente uma resposta padronizada.

## Proximas implementacoes

### Tools

Adicionar as ferramentas de dominio, seus schemas de entrada e saida, tratamento de falhas e registro no agente.

### Services

Implementar o endpoint FastAPI e o `agent_service`, incluindo pre-tratamento, pos-processamento, formatacao, guardrails e tratamento de erros.

### Memory

Definir como o historico sera identificado, armazenado, recuperado e limitado para cada conversa.

### Prompts

Criar o prompt de sistema e as instrucoes de uso das tools, regras de resposta e limites de comportamento.

## Docker

O `Dockerfile` instala as dependencias, copia o codigo da aplicacao e inicia o Uvicorn. Antes de usar em producao, a imagem deve receber uma versao especifica do Python e a configuracao de ambiente de forma segura.
