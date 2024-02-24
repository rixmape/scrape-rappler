import argparse
import json
import logging
import time

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Scrape articles from Rappler website.",
    )
    parser.add_argument(
        "--limit-article",
        type=int,
        metavar="N",
        help="limit the number of articles to scrape",
        default=None,
    )
    return parser.parse_args()


class SitemapScraper:
    def __init__(self, main_sitemap_url):
        self.main_sitemap_url = main_sitemap_url
        logging.info("SitemapScraper initialized with %s", main_sitemap_url)

    def fetch_main_sitemap(self):
        """Fetches the main sitemap and extracts the post sitemaps."""
        logging.info("Fetching main sitemap")
        try:
            response = requests.get(self.main_sitemap_url)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error("Failed to fetch main sitemap: %s", e)
            return []

        soup = BeautifulSoup(response.content, "xml")
        sitemap_tags = soup.find_all("sitemap")
        post_sitemaps = [
            tag.find("loc").text
            for tag in sitemap_tags
            if "post-sitemap" in tag.find("loc").text
        ]

        logging.info(
            "Fetched and parsed main sitemap. Post sitemaps found: %d",
            len(post_sitemaps),
        )
        return post_sitemaps

    def fetch_post_sitemaps(self, sitemaps, max_urls=None):
        """Fetches the post sitemaps and extracts the article URLs up to a specified limit."""
        article_urls = []
        for sitemap_url in sitemaps:
            if max_urls is not None and len(article_urls) >= max_urls:
                break  # Stop if desired number of URLs is reached

            logging.info("Fetching post sitemap from %s", sitemap_url)
            try:
                response = requests.get(sitemap_url)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logging.error("Failed to fetch post sitemap: %s", e)
                continue  # Skip to next sitemap

            soup = BeautifulSoup(response.content, "xml")
            urls = [url.loc.text for url in soup.findAll("url")]
            article_urls.extend(
                urls[: max_urls - len(article_urls)] if max_urls else urls
            )

            logging.info(
                "Fetched and parsed post sitemap. Articles found: %d",
                len(urls),
            )

        article_urls = list(set(article_urls))
        logging.info("Total unique articles found: %d", len(article_urls))
        return article_urls

    def get_article_urls(self, max_urls=None):
        """Fetches all article URLs from the main and post sitemaps."""
        logging.info("Starting the process to fetch all article URLs.")
        post_sitemaps = self.fetch_main_sitemap()
        if not post_sitemaps:
            logging.error("No post sitemaps found.")
            return []
        return self.fetch_post_sitemaps(post_sitemaps, max_urls=max_urls)


class RapplerScraper:
    ARTICLE_TITLE_XPATH = "//h1[contains(@class,'post-single__title')]"
    ARTICLE_CONTENT_XPATH = "//div[contains(@class,'post-single__content')]"
    VOTES_CONTAINER_XPATH = "//div[contains(@class,'xa3V2iPvKCrXH2KVimTv-g==')]"
    SEE_VOTES_XPATH = "//div[contains(@class,'AOhvJlN4Z5TsLqKZb1kSBw==')]"
    VOTE_DIV_XPATH = "//div[contains(@class,'i1IMtjULF3BKu3lB0m1ilg==')]"
    HAPPY_DIV_XPATH = "//div[contains(@class,'mood-happy')]"

    def __init__(self, article_url):
        self.article_url = article_url
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=options)
        logging.info("RapplerScraper initialized with %s", article_url)

    def setup(self):
        """Navigate to the article URL."""
        self.driver.get(self.article_url)
        logging.info("Navigated to article.")

    def wait_for(self, identifier, wait_time=10):
        """Wait for a specific element to be present."""
        logging.info("Waiting for element %s", identifier)
        return WebDriverWait(self.driver, wait_time).until(
            EC.presence_of_element_located((By.XPATH, identifier))
        )

    def click_element_via_js(self, identifier):
        """Clicks an element using JavaScript execution."""
        logging.info("Clicking element %s", identifier)
        element = self.wait_for(identifier)
        self.driver.execute_script("arguments[0].click();", element)

    def collect_votes_data(self):
        """Collects and formats votes data from the webpage."""
        logging.info("Collecting votes data.")
        votes_container = self.wait_for(self.VOTES_CONTAINER_XPATH)

        votes = [
            span.text
            for span in votes_container.find_elements(By.TAG_NAME, "span")
            if "%" in span.text
        ]
        moods = [
            heading.text
            for heading in votes_container.find_elements(By.TAG_NAME, "h4")
        ]

        return dict(zip(moods, votes))

    def scrape_article(self):
        logging.info("Starting to scrape article.")
        self.setup()
        data = {}

        try:
            title = self.wait_for(self.ARTICLE_TITLE_XPATH).text
            content = self.wait_for(self.ARTICLE_CONTENT_XPATH).text

            try:
                self.click_element_via_js(self.SEE_VOTES_XPATH)
            except:
                self.click_element_via_js(self.VOTE_DIV_XPATH)
                self.click_element_via_js(self.HAPPY_DIV_XPATH)

            votes_data = self.collect_votes_data()

            data = {
                "title": title,
                "url": self.article_url,
                "content": content,
                "votes": votes_data,
            }
        except Exception as e:
            logging.error("Failed to scrape article: %s", e)
        finally:
            self.driver.quit()
            logging.info("Finished scraping article.")

        return data


if __name__ == "__main__":
    args = parse_arguments()

    sitemap_url = "https://www.rappler.com/sitemap_index.xml"
    sitemap_scraper = SitemapScraper(sitemap_url)
    article_urls = sitemap_scraper.get_article_urls(max_urls=args.limit_article)

    data_list = []
    for url in article_urls:
        try:
            scraper = RapplerScraper(url)
            data = scraper.scrape_article()
            if data:
                data_list.append(data)
            time.sleep(1)  # Delay to avoid getting blocked
        except Exception as e:
            print(f"Failed to scrape {url}: {e}")

    with open("rappler_data.json", "w", encoding="utf-8") as f:
        json.dump(data_list, f)
