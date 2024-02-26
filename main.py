import argparse
import hashlib
import json
import logging
import os
from multiprocessing import Pool, cpu_count

from selenium.common.exceptions import TimeoutException
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(process)d - %(message)s",
)


class BaseScraper:
    def __init__(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("log-level=3")

        prefs = {"profile.managed_default_content_settings.images": 2}
        chrome_options.add_experimental_option("prefs", prefs)

        self.driver = webdriver.Chrome(options=chrome_options)

    def navigate_to_url(self, url):
        self.driver.get(url)

    def wait_for_element(self, identifier, by=By.XPATH, wait_time=10):
        return WebDriverWait(self.driver, wait_time).until(
            EC.presence_of_element_located((by, identifier))
        )

    def click_element_via_js(self, identifier, by=By.XPATH):
        element = self.wait_for_element(identifier, by=by)
        self.driver.execute_script("arguments[0].click();", element)

    def quit_driver(self):
        self.driver.quit()


class SitemapScraper(BaseScraper):
    """Scrape article URLs from the sitemaps of Rappler website."""

    BASE_URL = "https://www.rappler.com"

    def __init__(self, main_sitemap_url):
        super().__init__()
        self.main_sitemap_url = main_sitemap_url

    def _get_urls(self, condition):
        """Extract URLs from the current page based on the given condition."""
        urls = []
        for a in self.driver.find_elements(By.TAG_NAME, "a"):
            url = a.get_attribute("href")
            if condition(url):
                urls.append(url)
        return urls

    def _get_post_sitemaps(self):
        """Extract post sitemaps from the main sitemap."""
        logging.info("Fetching post sitemaps from %s...", self.main_sitemap_url)
        self.navigate_to_url(self.main_sitemap_url)
        return self._get_urls(lambda url: "post-sitemap" in url)

    def _get_article_urls(self, sitemap):
        """Extract article URLs from the given sitemap."""
        logging.info("Fetching article URLs from %s...", sitemap)
        self.navigate_to_url(sitemap)
        return self._get_urls(lambda url: url.startswith(self.BASE_URL))

    def scrape_sitemap(self, max_url=None):
        """Scrape certain number of article URLs from the sitemaps."""
        logging.info("Scraping article URLs from sitemaps...")
        post_sitemaps = self._get_post_sitemaps()
        urls = []
        for sitemap in post_sitemaps:
            new_urls = self._get_article_urls(sitemap)
            urls.extend(new_urls)
            if max_url is not None and len(urls) >= max_url:
                urls = urls[:max_url]
                break
        self.quit_driver()
        logging.info("Scraped %s article URLs.", len(urls))
        return urls


class RapplerScraper(BaseScraper):
    ARTICLE_TITLE_XPATH = "//h1[contains(@class,'post-single__title')]"
    ARTICLE_CONTENT_XPATH = "//div[contains(@class,'post-single__content')]"
    MOODS_CONTAINER_XPATH = "//div[contains(@class,'xa3V2iPvKCrXH2KVimTv-g==')]"
    SEE_MOODS_XPATH = "//div[contains(@class,'AOhvJlN4Z5TsLqKZb1kSBw==')]"
    VOTE_DIV_XPATH = "//div[contains(@class,'i1IMtjULF3BKu3lB0m1ilg==')]"
    HAPPY_DIV_XPATH = "//div[contains(@class,'mood-happy')]"

    def __init__(self, article_url):
        super().__init__()
        self.article_url = article_url

    def emulate_voting(self):
        try:
            logging.info("Emulating a vote...")
            self.click_element_via_js(self.VOTE_DIV_XPATH)
            self.click_element_via_js(self.HAPPY_DIV_XPATH)
        except TimeoutException:
            logging.error("Failed to emulate a vote.")
            raise TimeoutException  # To be caught by `scrape_article` method

    def attempt_moodmeter_interaction(self):
        try:
            logging.info("Checking for previous reactions...")
            self.click_element_via_js(self.SEE_MOODS_XPATH)
        except TimeoutException:
            logging.warning("No previous reactions found.")
            self.emulate_voting()

    def collect_moodmeter_data(self):
        logging.info("Fetching moodmeter data...")
        moods_container = self.wait_for_element(self.MOODS_CONTAINER_XPATH)
        moods = [
            heading.text
            for heading in moods_container.find_elements(By.TAG_NAME, "h4")
        ]
        percentages = [
            span.text
            for span in moods_container.find_elements(By.TAG_NAME, "span")
            if "%" in span.text
        ]
        return dict(zip(moods, percentages))

    def scrape_article(self):
        logging.info("Scraping article from %s...", self.article_url)
        self.navigate_to_url(self.article_url)
        article_data = {
            "url": self.article_url,
            "title": None,
            "content": None,
            "moods": None,
        }

        try:
            logging.info("Fetching title...")
            title = self.wait_for_element(self.ARTICLE_TITLE_XPATH).text
            article_data["title"] = title

            logging.info("Fetching content...")
            content = self.wait_for_element(self.ARTICLE_CONTENT_XPATH).text
            article_data["content"] = content

            logging.info("Triggering moodmeter interaction...")
            self.attempt_moodmeter_interaction()

            logging.info("Fetching moodmeter data...")
            moods = self.collect_moodmeter_data()
            article_data["moods"] = moods
        except TimeoutException as te:
            logging.error(f"A timeout occurred during scraping: {te}")
        except webdriver.common.exceptions.WebDriverException as we:
            logging.error(f"WebDriver error occurred: {we}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during scraping: {e}")
        finally:
            self.quit_driver()
            return article_data


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Scrape articles from Rappler website.",
    )
    parser.add_argument(
        "--main-sitemap",
        metavar="URL",
        help="URL of the main sitemap",
        default="https://www.rappler.com/sitemap_index.xml",
    )
    parser.add_argument(
        "--limit-article",
        type=int,
        metavar="N",
        help="limit the number of articles to scrape",
        default=None,
    )
    parser.add_argument(
        "--enable-multiprocessing",
        action="store_true",
        help="enable multiprocessing for scraping",
    )
    return parser.parse_args()


def scrape_and_save_article(url):
    scraper = RapplerScraper(url)
    data = scraper.scrape_article()
    save_to_json(data)


def save_to_json(data, output_dir="out"):
    url = data["url"]
    url_hash = hashlib.sha256(url.encode()).hexdigest()

    if all(value is not None for value in data.values()):
        directory = os.path.join(output_dir, "complete")
    else:
        missing_fields = [k for k, v in data.items() if v is None]
        logging.warning("Missing fields: %s.", ", ".join(missing_fields))
        directory = os.path.join(output_dir, "incomplete")

    os.makedirs(directory, exist_ok=True)

    filename = os.path.join(directory, f"{url_hash}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f)
    logging.info("Saved data to %s.", filename)


if __name__ == "__main__":
    args = parse_arguments()

    sitemap_scraper = SitemapScraper(args.main_sitemap)
    article_urls = sitemap_scraper.scrape_sitemap(
        max_url=args.limit_article,
    )

    if args.enable_multiprocessing:
        with Pool(processes=cpu_count()) as pool:
            pool.map(scrape_and_save_article, article_urls)
    else:
        for url in article_urls:
            scrape_and_save_article(url)
