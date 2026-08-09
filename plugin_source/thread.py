import asyncio
import traceback

from .utils import get_logger
logger = get_logger("ankicollab.thread")

def sync_run_async(async_function, *args, **kwargs):
    """Run an async function synchronously from a sync context with proper exception handling"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_function(*args, **kwargs))
    except Exception as e:
        logger.error(f"Exception in sync_run_async for {async_function.__name__}: {str(e)}")
        logger.error(traceback.format_exc())
        raise  # Re-raise in the calling context
    finally:
        loop.close()
