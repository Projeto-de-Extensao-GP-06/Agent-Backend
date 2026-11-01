# Implementação de Segurança - Agent Backend

## Resumo das Mudanças

Este documento descreve as camadas de segurança implementadas no Agent Backend (Python/FastAPI) para igualar o nível de segurança do Backend Java (Spring Boot).

## ✅ Camadas Implementadas

### 1. Autenticação JWT (`src/app/security/jwt_manager.py`)
- **Geração e validação de tokens JWT** usando HMAC-SHA256
- **Compatível com Backend Java**: mesma estrutura de claims (jti, sub, scope, authorities)
- **Hash de senhas** com BCrypt
- **Tokens de acesso e refresh** configuráveis via environment variables

### 2. Token Blacklist (`src/app/security/token_blacklist.py`)
- **Revogação imediata de tokens** (logout, comprometimento)
- **Armazenamento em memória thread-safe** usando ConcurrentHashMap
- **Limpeza automática de tokens expirados**
- **Baseado no JWT ID (jti)** para identificação única

### 3. Rate Limiter (`src/app/security/rate_limiter.py`)
- **Sliding window** para prevenir abuso
- **Mesmos limites do Backend Java**:
  - Login: 10/min, 30/hora
  - OTP: 5/min, 20/hora
  - Forms: 10/min, 60/hora
  - Geral: 60/min, 1000/hora
- **Thread-safe** usando locks

### 4. Middleware de Autenticação (`src/app/security/middleware.py`)
- **AuthCookieMiddleware**: Extrai token de cookie HttpOnly "authToken" PRIMEIRO
- **Fallback para header Authorization: Bearer** (Swagger, Postman, server-to-server)
- **Armazena token no estado da requisição** para uso posterior

### 5. Dependências de Autenticação (`src/app/security/auth.py`)
- **get_current_user**: Valida token e retorna email do usuário
- **get_current_user_optional**: Versão opcional (não exige token)
- **require_scope**: Verifica escopo específico (GENERAL_USE, SET_PASSWORD)
- **require_general_use**: Atalho para escopo GENERAL_USE
- **require_set_password**: Atalho para escopo SET_PASSWORD

### 6. Scheduler de Limpeza (`src/app/security/scheduler.py`)
- **Limpeza automática do token blacklist** a cada 30 minutos
- **Executado no startup** da aplicação
- **Assíncrono** usando asyncio

### 7. Utilitários de IP (`src/app/security/ip_utils.py`)
- **get_client_ip**: Extrai IP do cliente considerando proxies (X-Forwarded-For)
- **create_rate_limit_identifier**: Cria identificador único para rate limiting (IP + email)

### 8. CORS Configurado (`src/app/main.py`)
- **Origens específicas**: localhost:5173, localhost:3000
- **Credentials habilitados**
- **Métodos específicos**: GET, POST, PUT, PATCH, DELETE, OPTIONS
- **Headers expostos**: Content-Disposition

### 9. Rotas Protegidas (`src/app/routes/chat.py`)
- **POST /api/v1/chat**: Requer autenticação com escopo GENERAL_USE + rate limiting
- **DELETE /api/v1/chat/{session_id}**: Requer autenticação com escopo GENERAL_USE + rate limiting

### 10. Rotas de Autenticação (`src/app/routes/auth.py`)
- **GET /auth/validate**: Valida token e retorna informações do usuário
- **GET /auth/me**: Retorna usuário autenticado (requer escopo GENERAL_USE)
- **POST /auth/logout**: Revoga token e remove cookies
- **POST /auth/refresh-token**: Placeholder (delega para Backend Java)

## 📁 Arquivos Criados

```
src/app/security/
├── __init__.py
├── jwt_manager.py          # Gerenciador de tokens JWT
├── token_blacklist.py      # Serviço de blacklist de tokens
├── rate_limiter.py         # Rate limiter com sliding window
├── exceptions.py           # Exceções customizadas
├── auth.py                 # Dependências de autenticação FastAPI
├── middleware.py           # Middleware para extrair token de cookie
├── scheduler.py            # Scheduler de limpeza automática
└── ip_utils.py             # Utilitários de IP para rate limiting

src/app/routes/
└── auth.py                 # Rotas de autenticação
```

## 📝 Arquivos Modificados

```
requirements.txt                 # Adicionadas dependências JWT
src/app/config/settings.py      # Configurações JWT_SECRET, JWT_VALIDITY
src/app/main.py                 # Middleware, CORS, scheduler
src/app/routes/__init__.py      # Export auth_router
src/app/routes/chat.py          # Proteção de rotas + rate limiting
.env.example                    # Variáveis de ambiente documentadas
```

## 🔐 Configurações Necessárias

Adicione ao arquivo `.env`:

```env
JWT_SECRET=your-secret-key-change-in-production-min-32-bytes
JWT_VALIDITY=3600
JWT_REFRESH_VALIDITY=604800
```

**IMPORTANTE**: O `JWT_SECRET` deve ser o MESMO usado no Backend Java para que os tokens sejam compatíveis.

## 🚀 Como Usar

### Autenticação via Cookie HttpOnly
O frontend deve enviar o cookie `authToken` automaticamente (HttpOnly):
```javascript
// O browser envia automaticamente
fetch('http://localhost:8000/api/v1/chat', {
  method: 'POST',
  credentials: 'include',  // Importante!
  body: JSON.stringify({ message: 'Olá' })
})
```

### Autenticação via Header Bearer
Para Swagger, Postman ou chamadas server-to-server:
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "Olá"}'
```

## ⚠️ Limitações e Observações

1. **Refresh Token**: O endpoint `/auth/refresh-token` é um placeholder. Em produção, o refresh token deve ser validado no Backend Java que tem o banco de dados de usuários.

2. **Token Blacklist em Memória**: Atualmente armazenado em memória. Para produção com múltiplas instâncias, considere usar Redis.

3. **Scheduler**: O scheduler de limpeza é simples (asyncio). Para produção, considere usar APScheduler ou Celery.

4. **Validação de Usuário**: O Agent Backend valida o token mas não verifica se o usuário existe no banco. Em produção, considere fazer uma chamada ao Backend Java para validar o usuário.

## 🔄 Fluxo de Autenticação

```
1. Frontend faz login no Backend Java
2. Backend Java gera token JWT e define cookie HttpOnly "authToken"
3. Frontend faz requisição ao Agent Backend
4. Middleware extrai token do cookie "authToken"
5. Dependência get_current_user valida:
   - Token não está na blacklist
   - Assinatura válida
   - Token não expirado
   - Escopo correto (GENERAL_USE)
6. Rate limiter verifica limites por IP + email
7. Requisição é processada
```

## 🎯 Compatibilidade com Backend Java

| Feature | Backend Java | Agent Backend | Status |
|---------|--------------|---------------|--------|
| JWT (HMAC-SHA256) | ✅ | ✅ | ✅ Compatível |
| Cookie HttpOnly | ✅ | ✅ | ✅ Compatível |
| Header Bearer | ✅ | ✅ | ✅ Compatível |
| Token Blacklist | ✅ | ✅ | ✅ Compatível |
| Rate Limiter | ✅ | ✅ | ✅ Compatível |
| Refresh Token | ✅ | ⚠️ | ⚠️ Placeholder |
| Escopo (scope) | ✅ | ✅ | ✅ Compatível |
| CORS específico | ✅ | ✅ | ✅ Compatível |

## 📊 Testes Sugeridos

1. Testar autenticação com cookie HttpOnly
2. Testar autenticação com header Bearer
3. Testar rate limiting (fazer muitas requisições)
4. Testar token blacklist (logout e tentar usar token)
5. Testar validação de escopo (token com escopo errado)
6. Testar CORS (origens diferentes)
