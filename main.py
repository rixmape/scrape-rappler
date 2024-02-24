import argparse
import json
import logging
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class BaseScraper:
    def __init__(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("log-level=3")
        self.driver = webdriver.Chrome(options=chrome_options)

    def navigate_to_url(self, url):
        logging.info("Navigating to URL: %s", url)
        self.driver.get(url)

    def wait_for_element(self, identifier, by=By.XPATH, wait_time=10):
        logging.info("Waiting for element: %s", identifier)
        return WebDriverWait(self.driver, wait_time).until(
            EC.presence_of_element_located((by, identifier))
        )

    def click_element_via_js(self, identifier, by=By.XPATH):
        element = self.wait_for_element(identifier, by=by)
        self.driver.execute_script("arguments[0].click();", element)

    def quit_driver(self):
        self.driver.quit()


class SitemapScraper(BaseScraper):
    BASE_URL = "https://www.rappler.com"

    def __init__(self, main_sitemap_url):
        super().__init__()
        self.main_sitemap_url = main_sitemap_url

    def fetch_main_sitemap(self):
        self.navigate_to_url(self.main_sitemap_url)
        links = self.driver.find_elements(By.TAG_NAME, "a")
        return [
            url
            for link in links
            if "post-sitemap" in (url := link.get_attribute("href"))
        ]

    def fetch_post_sitemaps(self, sitemaps, max_urls=None):
        article_urls = []
        for sitemap in sitemaps:
            if max_urls is not None and len(article_urls) >= max_urls:
                logging.info("Reached max URLs.")
                break
            self.navigate_to_url(sitemap)
            urls = [
                url
                for a in self.driver.find_elements(By.TAG_NAME, "a")
                if (url := a.get_attribute("href")).startswith(self.BASE_URL)
            ]
            article_urls.extend(urls)
        if max_urls is not None:
            article_urls = article_urls[:max_urls]
        return article_urls

    def get_article_urls(self, max_urls=None):
        logging.info("Fetching article URLs.")
        post_sitemaps = self.fetch_main_sitemap()
        if not post_sitemaps:
            logging.error("No post sitemaps found.")
            return []
        urls = self.fetch_post_sitemaps(post_sitemaps, max_urls=max_urls)
        logging.info("Fetched %s article URLs.", len(urls))
        return urls


class RapplerScraper(BaseScraper):
    ARTICLE_TITLE_XPATH = "//h1[contains(@class,'post-single__title')]"
    ARTICLE_CONTENT_XPATH = "//div[contains(@class,'post-single__content')]"
    VOTES_CONTAINER_XPATH = "//div[contains(@class,'xa3V2iPvKCrXH2KVimTv-g==')]"
    SEE_VOTES_XPATH = "//div[contains(@class,'AOhvJlN4Z5TsLqKZb1kSBw==')]"

    def __init__(self, article_url):
        super().__init__()
        self.article_url = article_url

    def collect_votes_data(self):
        votes_container = self.wait_for_element(self.VOTES_CONTAINER_XPATH)
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
        logging.info("Scraping article: %s", self.article_url)
        self.navigate_to_url(self.article_url)
        data = {}

        try:
            title = self.wait_for_element(self.ARTICLE_TITLE_XPATH).text
            content = self.wait_for_element(self.ARTICLE_CONTENT_XPATH).text

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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

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
            time.sleep(1)
        except Exception as e:
            logging.error(f"Failed to scrape {url}: {e}")

    with open("rappler_data.json", "w", encoding="utf-8") as f:
        json.dump(data_list, f)
