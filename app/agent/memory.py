from langchain_core.runnables import RunnableConfig

from app.agent.agent import memory_store


def delete_thread(thread_id: str) -> bool:

    tupla = memory_store.get_tuple(RunnableConfig(configurable={"thread_id": thread_id}))

    if tupla is None:
        return False

    try:
        memory_store.delete_thread(thread_id)
    except Exception:
        pass

    return True