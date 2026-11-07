# ==========================================
# Estágio 1: Builder (Compilação e Instalação)
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Instala ferramentas essenciais de compilação sem manter lixo de cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Cria um virtualenv isolado com todas as dependências instaladas
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ==========================================
# Estágio 2: Imagem Final (Enxuta e Segura)
# ==========================================
FROM python:3.12-slim AS runner

WORKDIR /app

# Variáveis para otimizar execução Python em container
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Copia apenas o ambiente virtual já compilado (sem gcc ou arquivos temporários de build)
COPY --from=builder /opt/venv /opt/venv

# Cria usuário não-root por segurança e boas práticas semânticas
RUN useradd -u 1000 -m appuser && \
    chown -R appuser:appuser /app

# Copia o código da aplicação
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser .env.example .env

USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
