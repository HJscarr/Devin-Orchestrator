import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)


async def retry_async(coro_func, max_retries=3, base_delay=2.0):
    """Retry an async callable with exponential backoff."""
    for attempt in range(max_retries + 1):
        try:
            return await coro_func()
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
            if attempt == max_retries:
                logger.error("Request failed after %d retries: %s", max_retries, e)
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning("Request failed (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, max_retries, delay, e)
            await asyncio.sleep(delay)
