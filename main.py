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


class SitemapScraper:
    def __init__(self, main_sitemap_url):
        self.main_sitemap_url = main_sitemap_url
        logging.info(
            "SitemapScraper instance created with main sitemap URL: %s",
            main_sitemap_url,
        )

    def fetch_main_sitemap(self):
        """Fetches the main sitemap and extracts the post sitemaps."""
        logging.info(
            "Fetching main sitemap from %s",
            self.main_sitemap_url,
        )
        try:
            response = requests.get(self.main_sitemap_url)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error("Failed to fetch the main sitemap: %s", e)
            return []

        soup = BeautifulSoup(response.content, "xml")
        sitemap_tags = soup.find_all("sitemap")
        post_sitemaps = [
            tag.find("loc").text
            for tag in sitemap_tags
            if "post-sitemap" in tag.find("loc").text
        ]

        logging.info(
            "Successfully fetched and parsed main sitemap."
            " Post sitemaps found: %d",
            len(post_sitemaps),
        )
        return post_sitemaps

    def fetch_post_sitemaps(self, sitemaps):
        """Fetches the post sitemaps and extracts the article URLs."""
        article_urls = []
        for sitemap_url in sitemaps:
            logging.info("Fetching post sitemap from %s", sitemap_url)
            try:
                response = requests.get(sitemap_url)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logging.error("Failed to fetch the post sitemap: %s", e)
                continue  # Skip to the next sitemap

            soup = BeautifulSoup(response.content, "xml")
            urls = [url.loc.text for url in soup.findAll("url")]
            article_urls.extend(urls)
            logging.info(
                "Successfully fetched and parsed post sitemap."
                " Articles found: %d",
                len(urls),
            )

        article_urls = list(set(article_urls))
        logging.info(
            "Total unique article URLs extracted: %d",
            len(article_urls),
        )
        return article_urls

    def get_article_urls(self):
        """Main function to fetch all article URLs."""
        logging.info("Starting the process to fetch all article URLs.")
        post_sitemaps = self.fetch_main_sitemap()
        if not post_sitemaps:
            logging.error("No post sitemaps found.")
            return []
        return self.fetch_post_sitemaps(post_sitemaps)


class RapplerScraper:
    ARTICLE_TITLE_XPATH = "//h1[contains(@class,'post-single__title')]"
    ARTICLE_CONTENT_XPATH = "//div[contains(@class,'post-single__content')]"
    VOTES_CONTAINER_XPATH = "//div[contains(@class,'xa3V2iPvKCrXH2KVimTv-g==')]"
    SEE_VOTES_XPATH = "//div[contains(@class,'AOhvJlN4Z5TsLqKZb1kSBw==')]"
    VOTE_DIV_XPATH = "//div[contains(@class,'i1IMtjULF3BKu3lB0m1ilg==')]"
    HAPPY_DIV_XPATH = "//div[contains(@class,'mood-happy')]"

    def __init__(self, article_url):
        self.article_url = article_url
        self.driver = webdriver.Chrome()

    def setup(self):
        """Navigate to the article URL."""
        self.driver.get(self.article_url)

    def wait_for(self, identifier, wait_time=10):
        """Wait for a specific element to be present."""
        return WebDriverWait(self.driver, wait_time).until(
            EC.presence_of_element_located((By.XPATH, identifier))
        )

    def click_element_via_js(self, identifier):
        """Clicks an element using JavaScript execution."""
        element = self.wait_for(identifier)
        self.driver.execute_script("arguments[0].click();", element)

    def get_element_text(self, identifier, default=None):
        """Attempts to get an element's text, returning a default value if an error occurs."""
        try:
            return self.wait_for(identifier).text
        except:
            return default

    def collect_votes_data(self):
        """Collects and formats votes data from the webpage."""
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
        """Main function to scrape the article's title, content, and votes data."""
        self.setup()
        title = self.get_element_text(self.ARTICLE_TITLE_XPATH)
        content = self.get_element_text(self.ARTICLE_CONTENT_XPATH)

        try:
            try:
                self.click_element_via_js(self.SEE_VOTES_XPATH)
            except:
                self.click_element_via_js(self.VOTE_DIV_XPATH)
                self.click_element_via_js(self.HAPPY_DIV_XPATH)

            votes_data = self.collect_votes_data()
        except Exception as e:
            print(f"An error occurred while collecting votes data: {e}")
            votes_data = {}

        self.driver.quit()
        return {"title": title, "content": content, "votes": votes_data}


if __name__ == "__main__":
    sitemap_url = "https://www.rappler.com/sitemap_index.xml"
    sitemap_scraper = SitemapScraper(sitemap_url)
    article_urls = sitemap_scraper.get_article_urls()

    data_list = []
    for url in article_urls[:1]:
        try:
            scraper = RapplerScraper(url)
            data = scraper.scrape_article()
            data_list.append(data)
            time.sleep(1)  # Delay to avoid getting blocked
        except Exception as e:
            print(f"Failed to scrape {url}: {e}")

    with open("rappler_data.json", "w", encoding="utf-8") as f:
        json.dump(data_list, f)
