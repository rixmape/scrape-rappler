"""
This module contains the main script for scraping articles from the Rappler
website. It uses Selenium to navigate the website and extract article data.
"""

import argparse
import hashlib
import json
import logging
import multiprocessing as mp
import os
import time
from functools import partial

from seleniumwire import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    ":".join(
        [
            "%(asctime)s",
            "%(levelname)s",
            "%(process)d",
            "%(message)s",
        ]
    )
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


class ArticleData:
    """Class to store article data."""

    def __init__(self, url, title=None, content=None, moods=None):
        self.url = url
        self.title = title
        self.content = content
        self.moods = moods

    def is_complete(self):
        """Check if the article data is complete."""
        return all(value is not None for value in vars(self).values())

    def to_json(self):
        """Convert the article data to a JSON string."""
        return json.dumps(vars(self))

    def save(self, output_dir):
        """Save the article data to a JSON file."""
        url_hash = hashlib.sha256(self.url.encode()).hexdigest()
        directory = os.path.join(
            output_dir,
            "complete" if self.is_complete() else "incomplete",
        )
        os.makedirs(directory, exist_ok=True)
        filename = os.path.join(directory, f"{url_hash}.json")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        logger.info("Saved data to %s.", filename)


class BaseScraper:
    """Base class for web scraping using Selenium."""

    def __init__(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("log-level=3")
        chrome_options.add_experimental_option(
            "prefs",
            {"profile.managed_default_content_settings.images": 2},
        )
        self.driver = webdriver.Chrome(options=chrome_options)

    def navigate_to_url(self, url):
        """Navigate to the given URL."""
        self.driver.get(url)

    def get_urls(self, condition):
        """Extract URLs from the current page based on the given condition."""
        urls = []
        for a_tag in self.driver.find_elements(By.TAG_NAME, "a"):
            url = a_tag.get_attribute("href")
            if condition(url):
                urls.append(url)
        return urls

    def wait_for_element(self, identifier, by=By.XPATH, wait_time=100):
        """Wait for the element to be present in the DOM."""
        return WebDriverWait(self.driver, wait_time).until(
            EC.presence_of_element_located((by, identifier))
        )

    def click_element_via_js(self, identifier, by=By.XPATH):
        """Click the element using JavaScript."""
        element = self.wait_for_element(identifier, by=by)
        self.driver.execute_script("arguments[0].click();", element)

    def quit_driver(self):
        """Quit the WebDriver."""
        self.driver.quit()


class SitemapScraper(BaseScraper):
    """Scrape article URLs from the sitemaps of Rappler website."""

    BASE_URL = "https://www.rappler.com"

    def __init__(self, main_sitemap_url):
        super().__init__()
        self.main_sitemap_url = main_sitemap_url

    def _get_post_sitemaps(self):
        """Extract post sitemaps from the main sitemap."""
        self.loggerinfo(
            "Fetching post sitemaps from %s...", self.main_sitemap_url
        )
        self.navigate_to_url(self.main_sitemap_url)
        return self.get_urls(lambda url: "post-sitemap" in url)

    def _get_article_urls(self, sitemap):
        """Extract article URLs from the given sitemap."""
        logger.info("Fetching article URLs from %s...", sitemap)
        self.navigate_to_url(sitemap)
        return self.get_urls(lambda url: url.startswith(self.BASE_URL))

    def scrape_sitemap(self, max_url=None):
        """Scrape certain number of article URLs from the sitemaps."""
        logger.info("Scraping article URLs from sitemaps...")
        post_sitemaps = self._get_post_sitemaps()
        article_urls = []
        for sitemap in post_sitemaps:
            new_urls = self._get_article_urls(sitemap)
            article_urls.extend(new_urls)
            if max_url is not None and len(article_urls) >= max_url:
                article_urls = article_urls[:max_url]
                break
        self.quit_driver()
        logger.info("Scraped %s article URLs.", len(article_urls))
        return article_urls


class RapplerScraper(BaseScraper):
    """Scrape article data from Rappler website."""

    ARTICLE_TITLE_XPATH = "//h1[contains(@class,'post-single__title')]"
    ARTICLE_CONTENT_XPATH = "//div[contains(@class,'post-single__content')]"
    MOODS_CONTAINER_XPATH = "//div[contains(@class,'xa3V2iPvKCrXH2KVimTv-g==')]"
    SEE_MOODS_XPATH = "//div[contains(@class,'AOhvJlN4Z5TsLqKZb1kSBw==')]"
    VOTE_DIV_XPATH = "//div[contains(@class,'i1IMtjULF3BKu3lB0m1ilg==')]"
    HAPPY_DIV_XPATH = "//div[contains(@class,'mood-happy')]"
    VOTE_API_ENDPOINT = "/api/v1/votes"

    def __init__(self, article_url, output_dir):
        super().__init__()
        self.article_data = ArticleData(article_url)
        self.output_dir = output_dir

    def _emulate_voting(self):
        """Cast a vote on the mood to see reactions."""
        try:
            logger.info("Emulating a vote...")
            self.click_element_via_js(self.VOTE_DIV_XPATH)
            self.click_element_via_js(self.HAPPY_DIV_XPATH)
        except TimeoutException:
            logger.error("Failed to emulate a vote.")
            raise TimeoutException

    def _fetch_mood_data_from_requests(self):
        """Fetch mood data from the requests."""
        mood_data = None
        for request in self.driver.requests:
            if request.response and self.VOTE_API_ENDPOINT in request.url:
                logger.info("Vote API response received from %s.", request.url)
                raw_data = json.loads(request.response.body)
                mood_data = raw_data["data"]["mood_count"]
                break
        return mood_data

    def _fetch_title(self):
        """Fetch title from the article."""
        logger.info("Fetching title...")
        self.article_data.title = self.wait_for_element(
            self.ARTICLE_TITLE_XPATH
        ).text

    def _fetch_content(self):
        """Fetch content from the article."""
        logger.info("Fetching content...")
        self.article_data.content = self.wait_for_element(
            self.ARTICLE_CONTENT_XPATH
        ).text

    def _fetch_moods(self):
        """Fetch moods from the article."""
        logger.info("Fetching existing mood data...")
        time.sleep(1)  # TODO: Hack; replace by waiting for an element

        mood_data = self._fetch_mood_data_from_requests()
        if not mood_data:
            logger.info("Existing mood data not found.")
            self._emulate_voting()
            mood_data = self._fetch_mood_data_from_requests()

        if mood_data:
            self.article_data.moods = mood_data
        else:
            logger.error("Mood data not found.")

    def scrape_and_save(self):
        """Scrape article data and save it to a JSON file."""
        logger.info("Scraping article from %s...", self.article_data.url)
        self.navigate_to_url(self.article_data.url)

        try:
            self._fetch_title()
            self._fetch_content()
            self._fetch_moods()
        except TimeoutException as te:
            logger.error(f"A timeout occurred during scraping: {te}")
        except WebDriverException as we:
            logger.error(f"WebDriver error occurred: {we}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during scraping: {e}")
        finally:
            self.quit_driver()
            self.article_data.save(self.output_dir)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape articles from Rappler website.",
    )
    parser.add_argument(
        "-s",
        "--sitemap-url",
        metavar="URL",
        help="URL of the main sitemap",
        default="https://www.rappler.com/sitemap_index.xml",
    )
    parser.add_argument(
        "-m",
        "--max-articles",
        type=int,
        metavar="N",
        help="Maximum number of articles to scrape",
        default=None,
    )
    parser.add_argument(
        "-p",
        "--use-multiprocessing",
        action="store_true",
        help="Use multiprocessing for scraping",
    )
    parser.add_argument(
        "-o",
        "--output-directory",
        metavar="DIR",
        help="Directory to save the article data",
        default="article_data",
    )
    parser.add_argument(
        "-u",
        "--save-urls",
        action="store_true",
        help="Save the scraped article URLs to a file",
    )
    parser.add_argument(
        "-f",
        "--urls-file",
        metavar="FILE",
        help="File containing the article URLs",
        default=None,
    )
    parser.add_argument(
        "-i",
        "--ignore-cache",
        action="store_true",
        help="Ignore the cache and scrape the articles again",
    )
    return parser.parse_args()


def scrape_and_save_wrapper(url, output_dir, ignore_cache):
    if not ignore_cache:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        complete_dir = os.path.join(output_dir, "complete")
        incomplete_dir = os.path.join(output_dir, "incomplete")

        for directory in [output_dir, complete_dir, incomplete_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)

        for directory in [complete_dir, incomplete_dir]:
            if f"{url_hash}.json" in os.listdir(directory):
                logger.info("Article from %s is already scraped.", url)
                return None

    scraper = RapplerScraper(url, output_dir)
    scraper.scrape_and_save()


if __name__ == "__main__":
    args = parse_arguments()

    if args.urls_file:
        with open(args.urls_file, "r", encoding="utf-8") as f:
            article_urls = f.read().splitlines()
    else:
        scraper = SitemapScraper(args.sitemap_url)
        article_urls = scraper.scrape_sitemap(max_url=args.max_articles)

    if args.save_urls:
        time_now = int(time.time())
        filename = f"article_urls_{time_now}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(article_urls))

    if args.use_multiprocessing:
        workers = mp.cpu_count()
        with mp.Pool(processes=workers) as pool:
            func = partial(
                scrape_and_save_wrapper,
                output_dir=args.output_directory,
                ignore_cache=args.ignore_cache,
            )
            pool.map(func, article_urls)
    else:
        for url in article_urls:
            scrape_and_save_wrapper(
                url,
                args.output_directory,
                args.ignore_cache,
            )
