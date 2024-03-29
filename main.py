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

import firebase_admin
from firebase_admin import credentials, firestore
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire import webdriver


class ArticleData:
    """Class to store article data."""

    def __init__(
        self,
        url,
        title=None,
        datetime=None,
        content=None,
        moods=None,
    ):
        self.url = url
        self.url_hash = hashlib.sha256(url.encode()).hexdigest()
        self.title = title
        self.datetime = datetime
        self.content = content
        self.moods = moods

    def is_complete(self):
        """Check if the article data is complete."""
        return all(value is not None for value in vars(self).values())

    def to_json(self):
        """Convert the article data to a JSON string."""
        return json.dumps(vars(self), indent=4, ensure_ascii=False)

    def to_dict(self):
        """Convert the article data to a dictionary."""
        return vars(self)

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
        return filename


class BaseScraper:
    """Base class for web scraping using Selenium."""

    TIMEOUT_SECONDS = 120

    def __init__(self, disable_headless=False):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.setup_logger()

        chrome_options = webdriver.ChromeOptions()
        if not disable_headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("log-level=3")

        prefs = {
            "profile.default_content_setting_values": {
                "app_banner": 2,
                "auto_select_certificate": 2,
                "automatic_downloads": 2,
                # "cookies": 2,
                "durable_storage": 2,
                "fullscreen": 2,
                "geolocation": 2,
                "images": 2,
                # "javascript": 2,
                "media_stream_camera": 2,
                "media_stream_mic": 2,
                "media_stream": 2,
                "metro_switch_to_desktop": 2,
                "midi_sysex": 2,
                # "mixed_script": 2,
                "mouselock": 2,
                "notifications": 2,
                "plugins": 2,
                "popups": 2,
                "ppapi_broker": 2,
                "protected_media_identifier": 2,
                "protocol_handlers": 2,
                "push_messaging": 2,
                "site_engagement": 2,
                "ssl_cert_decisions": 2,
            }
        }
        chrome_options.add_experimental_option("prefs", prefs)

        self.driver = webdriver.Chrome(options=chrome_options)

    def setup_logger(self):
        """Setup the logger for the scraper."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            ":".join(
                [
                    "%(asctime)s",
                    "%(levelname)s",
                    "%(name)s",
                    "%(message)s",
                ]
            )
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

        if not self.logger.hasHandlers():  # Avoid duplicate handlers
            self.logger.addHandler(handler)

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

    def wait_for_element(
        self,
        identifier,
        by=By.CSS_SELECTOR,
        wait_time=TIMEOUT_SECONDS,
    ):
        """Wait for the element to be present in the DOM."""
        return WebDriverWait(self.driver, wait_time).until(
            EC.presence_of_element_located((by, identifier))
        )

    def click_element_via_js(self, identifier, by=By.CSS_SELECTOR):
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
        self.logger.info(
            "Fetching post sitemaps from %s...",
            self.main_sitemap_url,
        )
        self.navigate_to_url(self.main_sitemap_url)
        return self.get_urls(lambda url: "post-sitemap" in url)

    def _get_article_urls(self, sitemap):
        """Extract article URLs from the given sitemap."""
        self.logger.info("Fetching article URLs from %s...", sitemap)
        self.navigate_to_url(sitemap)
        return self.get_urls(lambda url: url.startswith(self.BASE_URL))

    def scrape_sitemap(self, max_url=None):
        """Scrape certain number of article URLs from the sitemaps."""
        self.logger.info("Scraping article URLs from sitemaps...")
        post_sitemaps = self._get_post_sitemaps()
        article_urls = []
        for sitemap in post_sitemaps:
            new_urls = self._get_article_urls(sitemap)
            article_urls.extend(new_urls)
            if max_url is not None and len(article_urls) >= max_url:
                article_urls = article_urls[:max_url]
                break
        self.quit_driver()
        self.logger.info("Scraped %s article URLs.", len(article_urls))
        return article_urls


class RapplerScraper(BaseScraper):
    """Scrape article data from Rappler website."""

    COLLECTION_NAME = "articles"
    ARTICLE_TITLE_CSS = ".post-single__title"
    ARTICLE_CONTENT_CSS = ".post-single__content"
    ARTICLE_DATETIME_CSS = ".post__timeago"
    MOODS_CONTAINER_CSS = r".xa3V2iPvKCrXH2KVimTv-g\=\="
    SEE_MOODS_CSS = r".AOhvJlN4Z5TsLqKZb1kSBw\=\="
    VOTE_DIV_CSS = r".i1IMtjULF3BKu3lB0m1ilg\=\="
    HAPPY_DIV_CSS = ".mood-happy"
    VOTE_API_ENDPOINT = "/api/v1/votes"
    SEE_MOODS_TIMEOUT_SECONDS = 30

    def __init__(
        self,
        article_url,
        output_dir,
        ignore_cache,
        save_to_firestore,
        firebase_credential_path,
        disable_headless,
    ):
        super().__init__(disable_headless=disable_headless)
        self.article_data = ArticleData(article_url)
        self.output_dir = output_dir
        self.ignore_cache = ignore_cache
        self.save_to_firestore = save_to_firestore
        self.firebase_credential_path = firebase_credential_path

        cred = credentials.Certificate(self.firebase_credential_path)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()

    def _is_article_in_local(self):
        url_hash = self.article_data.url_hash
        for subdir in ["complete", "incomplete"]:
            directory = os.path.join(self.output_dir, subdir)
            if os.path.exists(os.path.join(directory, f"{url_hash}.json")):
                return True
        return False

    def _is_article_in_firestore(self):
        """Check if the article already exists in Firestore."""
        url_hash = self.article_data.url_hash
        docs = (
            self.db.collection(self.COLLECTION_NAME)
            .where(field_path="url_hash", op_string="==", value=url_hash)
            .limit(1)
            .get()
        )
        return len(docs) > 0

    def _emulate_voting(self):
        """Cast a vote on the mood to see reactions."""
        try:
            self.logger.info("Emulating a vote...")
            self.click_element_via_js(self.VOTE_DIV_CSS)
            self.click_element_via_js(self.HAPPY_DIV_CSS)
        except TimeoutException:
            self.logger.error("Failed to emulate a vote.")
            raise TimeoutException

    def _fetch_mood_data_from_requests(self):
        """Fetch mood data from the requests."""
        self.logger.info("Fetching mood data from requests...")
        mood_data = None
        for request in self.driver.requests:
            if request.response and self.VOTE_API_ENDPOINT in request.url:
                self.logger.info(
                    "Vote API response received from %s.",
                    request.url,
                )
                raw_data = json.loads(
                    request.response.body.decode("utf-8", "ignore")
                )
                raw_data = raw_data["data"]["mood_count"]
                mood_data = {k.lower(): v for k, v in raw_data.items()}
                break
        return mood_data

    def _fetch_title(self):
        """Fetch title from the article."""
        self.logger.info("Fetching title...")
        self.article_data.title = self.wait_for_element(
            self.ARTICLE_TITLE_CSS
        ).text

    def _fetch_datetime(self):
        """Fetch datetime from the article."""
        self.logger.info("Fetching datetime...")
        self.article_data.datetime = self.wait_for_element(
            self.ARTICLE_DATETIME_CSS
        ).text

    def _fetch_content(self):
        """Fetch content from the article."""
        self.logger.info("Fetching content...")
        self.article_data.content = self.wait_for_element(
            self.ARTICLE_CONTENT_CSS
        ).text

    def _fetch_moods(self):
        """Fetch moods from the article."""
        mood_data = None

        try:
            self.logger.info("Checking existing mood data...")
            self.wait_for_element(
                self.SEE_MOODS_CSS,
                wait_time=self.SEE_MOODS_TIMEOUT_SECONDS,
            )
            mood_data = self._fetch_mood_data_from_requests()
        except TimeoutException:
            self.logger.info("Existing mood data not found.")
            self._emulate_voting()
            mood_data = self._fetch_mood_data_from_requests()

        if not mood_data:
            self.logger.error("Mood data not found.")

        self.article_data.moods = mood_data

    def _add_to_firestore(self):
        """Save the article data to Firestore."""
        if self.article_data.is_complete():
            doc_ref = self.db.collection(self.COLLECTION_NAME).document()
            doc_ref.set(self.article_data.to_dict())
            self.logger.info("Saved data to Firestore with ID %s.", doc_ref.id)
        else:
            self.logger.warning("Incomplete data not saved to Firestore.")

    def scrape_and_save(self):
        """Scrape article data and save it to a JSON file."""
        if (
            not self.ignore_cache
            and self.save_to_firestore
            and self._is_article_in_firestore()
        ):
            self.logger.info(
                "Article already exists in Firestore: %s. Skipping...",
                self.article_data.url,
            )
            return

        if not self.ignore_cache and self._is_article_in_local():
            self.logger.info(
                "Article already exists locally: %s. Skipping...",
                self.article_data.url,
            )
            return

        self.logger.info("Scraping article from %s...", self.article_data.url)
        self.navigate_to_url(self.article_data.url)

        try:
            self._fetch_title()
            self._fetch_datetime()
            self._fetch_content()
            self._fetch_moods()
        except TimeoutException as te:
            self.logger.error(f"A timeout occurred during scraping: {te}")
        except WebDriverException as we:
            self.logger.error(f"WebDriver error occurred: {we}")
        except Exception as e:
            self.logger.error(
                f"An unexpected error occurred during scraping: {e}"
            )
        finally:
            self.quit_driver()
            if self.save_to_firestore:
                self._add_to_firestore()
            else:
                filename = self.article_data.save(self.output_dir)
                self.logger.info("Saved data to %s.", filename)


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
    parser.add_argument(
        "-sf",
        "--save-to-firestore",
        action="store_true",
        help="Save the scraped article data to Firestore",
    )
    parser.add_argument(
        "-fc",
        "--firebase-credential-path",
        metavar="PATH",
        help="Path to the Firebase credential file",
        default="firebase-adminsdk.json",
    )
    parser.add_argument(
        "-dh",
        "--disable-headless",
        action="store_true",
        help="Disable headless mode for the browser",
    )
    return parser.parse_args()


def scraping_wrapper(url, args):
    """Wrapper function for scraping articles."""
    RapplerScraper(
        url,
        args.output_directory,
        args.ignore_cache,
        args.save_to_firestore,
        args.firebase_credential_path,
        args.disable_headless,
    ).scrape_and_save()


if __name__ == "__main__":
    args = parse_arguments()

    if args.urls_file:
        with open(args.urls_file, "r", encoding="utf-8") as f:
            article_urls = [line.strip() for line in f.readlines()]
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
            pool.map(
                partial(scraping_wrapper, args=args),
                article_urls,
            )
    else:
        for url in article_urls:
            scraping_wrapper(url, args)
