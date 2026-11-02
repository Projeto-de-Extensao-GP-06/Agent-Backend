import logging
from threading import Thread

from src.app.security.token_blacklist import token_blacklist

logger = logging.getLogger(__name__)


def cleanup_blacklist_task():
    """
    Tarefa síncrona em thread separada para limpeza periódica do token blacklist.

    Executa a cada 30 minutos (igual ao @Scheduled do Backend Java).
    Usa threading em vez de asyncio para maior compatibilidade com FastAPI.
    """
    import time

    while True:
        try:
            time.sleep(30 * 60)  # 30 minutos
            token_blacklist.cleanup_expired_tokens()
            logger.info("Limpeza do token blacklist concluída")
        except Exception as e:
            logger.error(f"Erro na limpeza do token blacklist: {e}")


def start_cleanup_scheduler():
    """
    Inicia o scheduler de limpeza do token blacklist.

    Esta função deve ser chamada no startup da aplicação.
    Usa uma thread daemon para não bloquear o shutdown da aplicação.
    """
    logger.info("Iniciando scheduler de limpeza do token blacklist")
    thread = Thread(target=cleanup_blacklist_task, daemon=True)
    thread.start()
