import asyncio
from datetime import datetime
from urllib.parse import quote

import nodriver as uc

from src.core.logger import logger
from src.core.settings import settings
from src.parser.browser import find_sku_position, open_page_with_blocking
from src.services.sheets import get_sku_with_queries, insert_results_column, write_result


async def sheets_writer(queue: asyncio.Queue) -> None:
    """Background task that writes results to Google Sheets."""
    while True:
        item = await queue.get()
        if item is None:  # Poison pill to stop
            queue.task_done()
            break

        row, value, is_found = item
        try:
            # Run blocking gspread call in thread pool
            await asyncio.get_event_loop().run_in_executor(
                None, write_result, row, value, is_found
            )
            logger.debug(f"Written to row {row}: {value}")
        except Exception as e:
            logger.error(f"Failed to write to row {row}: {e}")
        finally:
            queue.task_done()


async def main() -> None:
    sku_data = get_sku_with_queries()
    logger.info(f"Found {len(sku_data)} SKUs to process")

    if not sku_data:
        logger.warning("No SKUs to process")
        return

    # Insert new column D with timestamp header
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    logger.info(f"Inserting new column D: {timestamp}")
    insert_results_column(timestamp)

    # Start background writer
    write_queue: asyncio.Queue = asyncio.Queue()
    writer_task = asyncio.create_task(sheets_writer(write_queue))

    browser = await uc.start()
    logger.info("Browser started")

    for item in sku_data:
        sku = item["sku"]
        queries = item["queries"]
        logger.info(f"Processing SKU: {sku} ({len(queries)} queries)")

        for query_data in queries:
            query = query_data["query"]
            row = query_data["row"]
            search_url = settings.ozon_search_url + quote(query)
            logger.info(f"Query: {query}")
            logger.debug(f"URL: {search_url}")

            max_retries = 3
            result = None

            for attempt in range(max_retries):
                if attempt > 0:
                    logger.info(f"Retry {attempt}/{max_retries} for query: {query}")

                tab = await open_page_with_blocking(browser, search_url)
                await asyncio.sleep(3)  # Wait for initial load

                result = await find_sku_position(tab, sku)

                # Check if we need to retry (page didn't load enough products)
                if result and result.get("needs_retry"):
                    products_found = result.get("products_found", 0)
                    logger.warning(f"Page incomplete ({products_found} products), reloading...")
                    await tab.close()
                    result = None
                    await asyncio.sleep(1)
                    continue

                # Got a valid result or reached 1000+ items
                break

            if result and "position" in result:
                position = result["position"]
                is_found = position < 1000
                value = str(position) if is_found else "1000+"
                logger.info(f"Position: {position} -> writing '{value}' to row {row}")
            else:
                value = "1000+"
                is_found = False
                logger.warning(f"SKU {sku} not found for query: {query} -> writing '1000+'")

            # Queue result for async writing (non-blocking)
            await write_queue.put((row, value, is_found))

    # Stop writer and wait for all writes to complete
    await write_queue.put(None)  # Poison pill
    await write_queue.join()
    await writer_task

    logger.info("Done!")
    browser.stop()


if __name__ == "__main__":
    uc.loop().run_until_complete(main())
