"""
This module scrapes the article URLs from the sitemap of Rappler's website.
"""

import hashlib
import logging
import os
import asyncio
from aiohttp import ClientSession

from bs4 import BeautifulSoup


OUTPUT_PATH = "article_urls"
MAIN_SITEMAP = "https://www.rappler.com/sitemap_index.xml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(message)s",
)


async def get_response(
    url: str,
    session: ClientSession,
) -> str | None:
    """Get the response from the given URL."""
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text()
    except Exception as err:
        logging.error("Failed to get response from %s: %s", url, err)
        return None


async def parse_sitemap(
    url: str,
    identifier: str,
    session: ClientSession,
) -> list[str]:
    """Parse the sitemap and return the tags with the given identifier."""
    response = await get_response(url, session)
    if response is not None:
        soup = BeautifulSoup(response, features="xml")
        return soup.find_all(identifier)
    else:
        return []


async def get_sitemaps(
    main_sitemap: str,
    session: ClientSession,
) -> list[str]:
    """Get the post sitemaps from the main sitemap."""
    logging.info("Fetching post sitemaps from %s...", main_sitemap)
    sitemap_tags = await parse_sitemap(main_sitemap, "sitemap", session)
    post_sitemaps = [
        tag.find("loc").text
        for tag in sitemap_tags
        if "post-sitemap" in tag.find("loc").text
    ]
    return post_sitemaps


async def scrape_article_urls(
    url: str,
    output_dir: str,
    session: ClientSession,
) -> None:
    """Scrape the article URLs from the given sitemap URL."""
    logging.info("Fetching article URLs from %s...", url)
    url_tags = await parse_sitemap(url, "url", session)
    article_urls = [tag.find("loc").text for tag in url_tags]
    write_to_file(article_urls, output_dir)


def write_to_file(
    urls: list[str],
    output_dir: str,
) -> None:
    """Write the article URLs to a file."""
    os.makedirs(output_dir, exist_ok=True)
    url_hash = hashlib.md5(urls[0].encode()).hexdigest()
    filename = f"{url_hash}.txt"
    logging.info("Writing article URLs to %s...", filename)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w") as f:
        f.write("\n".join(urls))


async def main() -> None:
    async with ClientSession() as session:
        post_sitemaps = await get_sitemaps(MAIN_SITEMAP, session)
        tasks = [
            scrape_article_urls(url, OUTPUT_PATH, session)
            for url in post_sitemaps
        ]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
