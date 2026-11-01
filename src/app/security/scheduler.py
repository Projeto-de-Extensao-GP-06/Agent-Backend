import asyncio
import logging

from src.app.security.token_blacklist import token_blacklist

logger = logging.getLogger(__name__)


async def cleanup_blacklist_task():
    """
    Tarefa assíncrona para limpeza periódica do token blacklist.

    Executa a cada 30 minutos (igual ao @Scheduled do Backend Java).
    """
    while True:
        try:
            await asyncio.sleep(30 * 60)  # 30 minutos
            token_blacklist.cleanup_expired_tokens()
            logger.info("Limpeza do token blacklist concluída")
        except asyncio.CancelledError:
            logger.info("Scheduler de limpeza do token blacklist cancelado")
            break
        except Exception as e:
            logger.error(f"Erro na limpeza do token blacklist: {e}")


def start_cleanup_scheduler():
    """
    Inicia o scheduler de limpeza do token blacklist.

    Esta função deve ser chamada no startup da aplicação.
    """
    logger.info("Iniciando scheduler de limpeza do token blacklist")
    asyncio.create_task(cleanup_blacklist_task())
