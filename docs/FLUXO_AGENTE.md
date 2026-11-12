# Fluxo do Agente MarIA

## 1. Visão geral (sequência ponta a ponta)

```mermaid
sequenceDiagram
    autonumber
    actor U as Cliente (front)
    participant MW as AuthCookieMiddleware + CORS
    participant R as routes/chat.py<br/>POST /api/v1/chat
    participant SEC as Auth JWT (GENERAL_USE)<br/>+ rate_limiter
    participant S as agent_service<br/>executarPipelineAgente
    participant AN as Anonymizer<br/>(Presidio + AES encrypt)
    participant G as Grafo LangGraph<br/>(checkpointer memory_store)
    participant LLM as Gemini<br/>(ChatGoogleGenerativeAI)
    participant T as ToolNode (testeTool)
    participant DE as Desanonimizador<br/>(AES decrypt)
    participant GR as 🚧 Guardrails (WIP)

    U->>MW: message, session_id?, dados_processo?
    MW->>R: extrai token (cookie authToken / Bearer)
    R->>SEC: require_general_use + check_rate_limit
    alt token inválido / limite excedido
        SEC-->>U: 401 / 403 / 429
    end
    R->>R: idSessao = session_id ou uuid4()
    R->>S: mensagem, idSessao, dadosProcesso
    S->>S: strip() e valida vazio
    alt mensagem vazia
        S-->>R: ValueError
        R-->>U: 400
    end
    S->>AN: transformarDadosProcessoIn (recursivo)
    AN-->>S: dados_processo anonimizado
    S->>AN: transformarMensagemIn
    AN-->>S: mensagem com tokens criptografados
    rect rgba(111, 66, 193, 0.35)
    Note over S,GR: 🚧 WIP (futuro): guardrails de entrada
    S-->>GR: validar mensagem anonimizada
    GR-->>S: aprovada / bloqueada
    end
    S->>G: ainvoke({messages:[HumanMessage], dados_processo}, thread_id=idSessao)
    loop até não haver tool_calls
        G->>G: node agent: build_message (SYSTEM_PROMPT + DADOS DO PROCESSO)
        G->>LLM: ainvoke(mensagens)
        LLM-->>G: AIMessage (llm_calls + 1)
        alt há tool_calls
            G->>T: should_continue → "tools"
            T-->>G: ToolMessage (resultado)
        end
    end
    G-->>S: state final (messages, llm_calls, dados_processo)
    S->>S: conteudoParaTexto(messages[-1])
    rect rgba(111, 66, 193, 0.35)
    Note over S,GR: 🚧 WIP (futuro): guardrails de saída
    S-->>GR: validar resposta do LLM
    GR-->>S: aprovada / bloqueada / reescrita
    end
    S->>DE: transformarDadosProcessoOut
    DE-->>S: texto com dados originais
    alt sem resposta / erro interno
        S-->>R: RuntimeError / Exception
        R-->>U: 502
    end
    S-->>R: resposta, raw_response, debug_info
    R-->>U: 200 ChatResponse(resumo_response{response, session_id}, raw_response)
```

## 2. Anonimização / desanonimização

```mermaid
flowchart LR
    A[Texto ou dict do processo] --> B{Tipo}
    B -- dict/list --> C[Percorre recursivamente]
    C --> D
    B -- str --> D[Presidio AnalyzerEngine<br/>idioma 'pt' + recognizers custom]
    D --> E[Filtra IGNORAR_ENTIDADES]
    E --> F{Há PII?}
    F -- não --> G[Texto original]
    F -- sim --> H[AnonymizerEngine<br/>operador encrypt AES<br/>chave: anonymization_key]
    H --> I[Texto com tokens criptografados]
    I --> LLM[(LLM só vê tokens)]
    LLM --> J[Resposta do LLM]
    J --> K[Regex ENCRYPTED_TOKEN_PATTERN]
    K --> L{AESCipher.decrypt OK?}
    L -- não --> M[Mantém palavra]
    L -- sim --> N[DeanonymizeEngine decrypt]
    N --> O[Resposta com dados reais ao usuário]
```

## 3. Grafo LangGraph (nodes, edges e estado)

```mermaid
flowchart TD
    START((START)) --> AG
    subgraph STATE[AgentState + checkpointer por thread_id]
        direction LR
        s1[messages: add_messages]
        s2[dados_processo: reducer preserva se vier None]
        s3[llm_calls]
    end
    AG["node: agent<br/>build_message → SYSTEM_PROMPT + dados_processo<br/>model.bind_tools([testeTool]).ainvoke"]
    AG --> SC{"should_continue<br/>última msg tem tool_calls?"}
    SC -- sim --> TL["node: tools (ToolNode)<br/>executa testeTool"]
    TL -- ToolMessage --> AG
    SC -- não --> END((END))
```

## 4. 🚧 Guardrails (WIP — ainda não implementado)

> [!WARNING]
> Seção **Work In Progress**: os guardrails ainda não existem no código. Posições e comportamentos abaixo são planejados e podem mudar.

```mermaid
flowchart TD
    IN[Mensagem anonimizada] --> GI
    GI["🚧 WIP: Guardrail de ENTRADA<br/>ex.: prompt injection, off-topic, conteúdo proibido"]
    GI -- bloqueada --> BL1[Resposta padrão de recusa]
    GI -- aprovada --> AG[node agent / LLM / tools]
    AG --> GO["🚧 WIP: Guardrail de SAÍDA<br/>ex.: vazamento de tokens/PII, alucinação, tom e política"]
    GO -- bloqueada --> BL2[Resposta padrão de recusa]
    GO -- reescrita --> RW[Resposta ajustada]
    GO -- aprovada --> DE[Desanonimização]
    RW --> DE
    DE --> OUT[Resposta ao usuário]

    style GI fill:#6f42c1,stroke:#d6c4f5,color:#ffffff,stroke-dasharray: 5 5
    style GO fill:#6f42c1,stroke:#d6c4f5,color:#ffffff,stroke-dasharray: 5 5
```

Ponto de integração previsto: em `executarPipelineAgente`, antes do `ainvoke` (entrada) e antes de `transformarDadosProcessoOut` (saída). A alternativa é incluí-los como nodes no grafo LangGraph.

## 5. Mapa de erros

```mermaid
flowchart LR
    R1[Request] --> A1{JWT válido?}
    A1 -- não --> E1[401/403]
    A1 -- sim --> A2{Rate limit ok?}
    A2 -- não --> E2[429]
    A2 -- sim --> A3{Mensagem vazia?}
    A3 -- sim --> E3[400]
    A3 -- não --> A4{Pipeline/LLM ok?}
    A4 -- não --> E4[502]
    A4 -- sim --> OK[200 ChatResponse]
```

> [!NOTE]
> Hoje há apenas uma tool (`testeTool`). Novas tools entram na lista `ferramentas` em `agent/agent.py` e o `ToolNode` as expõe automaticamente ao LLM, que escolhe qual chamar via `tool_calls`.
