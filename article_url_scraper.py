"""
This module scrapes the article URLs from the sitemap of Rappler's website.
"""

import hashlib
import logging
import os
from multiprocessing import Pool, cpu_count

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = "article_urls"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(process)d:%(message)s",
)


def get_response(url: str) -> requests.Response | None:
    """Get the response from the given URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as err:
        logging.error("Failed to get response from %s: %s", url, err)
        return None
    return response


def parse_sitemap(url: str, identifier: str) -> list[str]:
    """Parse the sitemap and return the tags with the given identifier."""
    response = get_response(url)
    if response is not None:
        soup = BeautifulSoup(response.text, features="xml")
        return soup.find_all(identifier)
    else:
        return []


def get_sitemaps(main_sitemap: str) -> list[str]:
    """Get the post sitemaps from the main sitemap."""
    logging.info("Fetching post sitemaps from %s...", main_sitemap)
    sitemap_tags = parse_sitemap(main_sitemap, "sitemap")
    post_sitemaps = [
        tag.find("loc").text
        for tag in sitemap_tags
        if "post-sitemap" in tag.find("loc").text
    ]
    return post_sitemaps


def scrape_article_urls(url: str) -> None:
    logging.info("Fetching article URLs from %s...", url)
    url_tags = parse_sitemap(url, "url")
    article_urls = [tag.find("loc").text for tag in url_tags]
    write_to_file(article_urls)


def write_to_file(article_urls):
    url_hash = hashlib.md5(article_urls[0].encode()).hexdigest()
    filename = f"{url_hash}.txt"
    logging.info("Writing article URLs to %s...", filename)
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w") as f:
        f.write("\n".join(article_urls))


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    main_sitemap = "https://www.rappler.com/sitemap_index.xml"
    post_sitemaps = get_sitemaps(main_sitemap)

    with Pool(processes=cpu_count()) as pool:
        pool.map(scrape_article_urls, post_sitemaps)
        pool.close()
        pool.join()
