import logging
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)

memory_store = InMemorySaver()


def delete_thread(thread_id: str) -> bool:
    tupla = memory_store.get_tuple(RunnableConfig(configurable={"thread_id": thread_id}))

    if tupla is None:
        return False

    try:
        memory_store.delete_thread(thread_id)
    except Exception as e:
        logger.error("Erro ao deletar thread %s: %s", thread_id, e)
        return False

    return True


__all__ = ["memory_store", "delete_thread"]