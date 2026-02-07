import asyncio
from urllib.parse import quote

import nodriver as uc

from src.core.logger import logger
from src.core.settings import settings
from src.parser.browser import find_sku_position
from src.services.sheets import get_sku_with_queries


async def main() -> None:
    sku_data = get_sku_with_queries()
    logger.info(f"Found {len(sku_data)} SKUs to process")

    if not sku_data:
        logger.warning("No SKUs to process")
        return

    browser = await uc.start()
    logger.info("Browser started")

    for item in sku_data:
        sku = item["sku"]
        queries = item["queries"]
        logger.info(f"Processing SKU: {sku} ({len(queries)} queries)")

        for query in queries:
            search_url = settings.ozon_search_url + quote(query)
            logger.info(f"Query: {query}")
            logger.debug(f"URL: {search_url}")

            tab = await browser.get(search_url)
            await asyncio.sleep(2)  # Wait for initial load

            result = await find_sku_position(tab, sku)

            if result:
                logger.info(f"Position: {result['position']} (total scanned: {result['total_items']})")
            else:
                logger.warning(f"SKU {sku} not found for query: {query}")

    logger.info("Done!")
    browser.stop()


if __name__ == "__main__":
    uc.loop().run_until_complete(main())
