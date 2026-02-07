import asyncio
import json as json_module
import re

import nodriver as uc

from src.core.logger import logger
from src.core.settings import settings

SKU_PATTERN = re.compile(r"/product/[^/]+-(\d+)/")

JS_GET_PRODUCTS = """
(() => {
    const tiles = document.querySelectorAll('[class*="tile-root"]');
    const products = [];
    for (const tile of tiles) {
        const link = tile.querySelector('a[href*="/product/"]');
        if (link) {
            products.push(link.href);
        }
    }
    return JSON.stringify(products);
})()
"""


async def start_browser() -> uc.Browser:
    """Start nodriver browser instance."""
    return await uc.start()


async def open_page(browser: uc.Browser, url: str | None = None) -> uc.Tab:
    """Open page in browser using nodriver."""
    target_url = url or settings.ozon_search_url
    return await browser.get(target_url)


def extract_sku(href: str) -> str | None:
    """Extract SKU from product URL."""
    match = SKU_PATTERN.search(href)
    return match.group(1) if match else None


def _unwrap_js_value(result):
    """Unwrap nodriver's wrapped JS values like {'type': 'string', 'value': '...'} or {'type': 'array', 'value': [...]}."""
    if isinstance(result, dict) and "type" in result and "value" in result:
        value = result["value"]
        if isinstance(value, list):
            return [_unwrap_js_value(item) for item in value]
        return value
    if isinstance(result, list):
        return [_unwrap_js_value(item) for item in result]
    return result


async def get_product_hrefs(tab: uc.Tab) -> list[str]:
    """Get product hrefs from current page state."""
    result = await tab.evaluate(JS_GET_PRODUCTS)

    # Debug: log raw result type
    logger.debug(f"JS_GET_PRODUCTS raw result type: {type(result).__name__}, value preview: {str(result)[:200]}")

    # Unwrap nodriver's wrapped values
    result = _unwrap_js_value(result)

    # Parse JSON string result
    hrefs = []
    if isinstance(result, str):
        try:
            hrefs = json_module.loads(result)
        except json_module.JSONDecodeError:
            logger.warning(f"Failed to parse JS result as JSON: {result[:100]}")
    elif isinstance(result, list):
        hrefs = result

    logger.debug(f"Extracted {len(hrefs)} hrefs")

    return [h for h in hrefs if isinstance(h, str)]


async def wait_for_products(tab: uc.Tab, timeout: float = 10.0) -> bool:
    """Wait for products to appear on page."""
    logger.debug(f"Waiting for products (timeout={timeout}s)")
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        hrefs = await get_product_hrefs(tab)
        if hrefs:
            logger.debug(f"Products appeared: {len(hrefs)} items")
            return True
        await asyncio.sleep(0.5)

    # Debug: dump page structure to find correct selectors
    logger.warning("Timeout waiting for products - dumping page structure for debugging")
    debug_js = """
    (() => {
        const results = {};

        // Check various possible selectors
        results.tile_root = document.querySelectorAll('[class*="tile-root"]').length;
        results.tile_hover = document.querySelectorAll('[class*="tile-hover"]').length;
        results.product_card = document.querySelectorAll('[class*="product-card"]').length;
        results.widget_search = document.querySelectorAll('[class*="widget-search-result"]').length;
        results.search_result = document.querySelectorAll('[class*="search-result"]').length;
        results.product_links = document.querySelectorAll('a[href*="/product/"]').length;
        results.all_links = document.querySelectorAll('a').length;

        // Get sample of classes on divs near product links
        const productLink = document.querySelector('a[href*="/product/"]');
        if (productLink) {
            results.product_link_href = productLink.href;
            let parent = productLink.parentElement;
            results.parent_classes = [];
            for (let i = 0; i < 5 && parent; i++) {
                results.parent_classes.push(parent.className || '(no class)');
                parent = parent.parentElement;
            }
        }

        // Get body content length to verify page loaded
        results.body_length = document.body.innerHTML.length;
        results.url = window.location.href;

        return results;
    })()
    """
    debug_result = await tab.evaluate(debug_js)
    logger.warning(f"Page debug info: {debug_result}")

    return False


async def find_sku_position(
    tab: uc.Tab,
    target_sku: str,
    max_items: int = 1000,
    scroll_step: int = 2000,
    min_delay: float = 0.15,
    load_wait: float = 0.5,
    stale_threshold: int = 5,
) -> dict | None:
    """
    Find SKU position in search results with adaptive scrolling.

    Returns:
        {'sku': str, 'position': int, 'total_items': int} or None if not found
    """
    logger.info(f"Searching for SKU: {target_sku}")
    logger.debug(f"Params: max_items={max_items}, scroll_step={scroll_step}, stale_threshold={stale_threshold}")

    if not await wait_for_products(tab):
        logger.warning(f"No products loaded for SKU {target_sku}")
        return None

    # Debug: check initial page state
    current_url = await tab.evaluate("window.location.href")
    scroll_height = await tab.evaluate("document.documentElement.scrollHeight")
    viewport_height = await tab.evaluate("window.innerHeight")
    scroll_y = await tab.evaluate("window.scrollY")
    logger.debug(f"Initial state: URL={current_url}")
    logger.debug(f"Page dimensions: scrollHeight={scroll_height}, viewportHeight={viewport_height}, scrollY={scroll_y}")

    seen_skus: dict[str, int] = {}
    stale_count = 0
    scroll_count = 0

    while len(seen_skus) < max_items:
        prev_count = len(seen_skus)  # Запоминаем ДО парсинга

        # Get current products via JS
        hrefs = await get_product_hrefs(tab)
        logger.debug(f"Scroll #{scroll_count}: got {len(hrefs)} hrefs from DOM")

        # Debug: log scroll position before each iteration
        current_scroll_y = await tab.evaluate("window.scrollY")
        current_scroll_height = await tab.evaluate("document.documentElement.scrollHeight")
        logger.debug(f"Scroll position: scrollY={current_scroll_y}, scrollHeight={current_scroll_height}")

        # Parse SKUs and track positions
        new_this_round = 0
        for href in hrefs:
            sku = extract_sku(href)
            if sku and sku not in seen_skus:
                position = len(seen_skus) + 1
                seen_skus[sku] = position
                new_this_round += 1
                logger.debug(f"New SKU at position {position}: {sku}")

                if sku == target_sku:
                    logger.info(f"FOUND SKU {target_sku} at position {position}")
                    return {
                        "sku": sku,
                        "position": position,
                        "total_items": len(seen_skus),
                    }

        current_count = len(seen_skus)
        logger.debug(f"Total unique SKUs: {current_count} (+{new_this_round} new)")

        # Log progress only when new items found (avoid spam)
        if new_this_round > 0:
            logger.info(f"Progress: {current_count}/{max_items} positions checked (+{new_this_round} new)")

        # Check if new items appeared
        if current_count == prev_count:
            stale_count += 1
            logger.debug(f"No new products, stale_count={stale_count}/{stale_threshold}")
            if stale_count >= stale_threshold:
                logger.info(f"End of results reached after {scroll_count} scrolls, {current_count} products")
                break
            await asyncio.sleep(load_wait)
        else:
            stale_count = 0
            await asyncio.sleep(min_delay)

        # Scroll using JS (more reliable than scroll_down)
        scroll_count += 1
        scroll_before = await tab.evaluate("window.scrollY")
        await tab.evaluate(f"window.scrollBy(0, {scroll_step})")
        scroll_after = await tab.evaluate("window.scrollY")
        actual_scroll = scroll_after - scroll_before
        logger.debug(f"Scroll #{scroll_count}: requested={scroll_step}px, actual={actual_scroll}px (scrollY: {scroll_before} -> {scroll_after})")

        # Debug: check if we've reached the bottom
        max_scroll = await tab.evaluate("document.documentElement.scrollHeight - window.innerHeight")
        if scroll_after >= max_scroll - 10:
            logger.debug(f"Reached bottom of page (scrollY={scroll_after}, maxScroll={max_scroll})")

    if len(seen_skus) >= max_items:
        logger.info(f"Reached max_items limit ({max_items}), moving to next query")
    logger.warning(f"SKU {target_sku} not found in {len(seen_skus)} products")
    return None