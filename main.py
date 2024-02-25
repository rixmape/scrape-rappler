import argparse
import hashlib
import json
import logging
import os
from multiprocessing import Pool, cpu_count

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class BaseScraper:
    def __init__(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("log-level=3")
        chrome_options.add_argument("--disable-extensions")

        prefs = {"profile.managed_default_content_settings.images": 2}
        chrome_options.add_experimental_option("prefs", prefs)

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
        post_sitemaps = [
            url
            for link in links
            if "post-sitemap" in (url := link.get_attribute("href"))
        ]
        logging.info("Found %s post sitemaps.", len(post_sitemaps))
        return post_sitemaps

    def fetch_post_sitemaps(self, sitemaps, max_urls=None, ignore_urls=None):
        if ignore_urls is None:
            ignore_urls = []
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
                and url not in ignore_urls
            ]
            article_urls.extend(urls)
        if max_urls is not None:
            article_urls = article_urls[:max_urls]
        return article_urls

    def scrape_sitemap(self, max_urls=None, ignore_urls=None):
        try:
            logging.info("Fetching article URLs.")
            post_sitemaps = self.fetch_main_sitemap()
            if not post_sitemaps:
                logging.error("No post sitemaps found.")
                return []
            urls = self.fetch_post_sitemaps(
                post_sitemaps,
                max_urls=max_urls,
                ignore_urls=ignore_urls,
            )
            logging.info("Fetched %s article URLs.", len(urls))
        except Exception as e:
            logging.error("Failed to scrape sitemap: %s", e)
            return []
        finally:
            self.quit_driver()
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

    def collect_moodmeter_data(self):
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
        logging.info("Scraping article: %s", self.article_url)
        self.navigate_to_url(self.article_url)
        article_data = {}

        try:
            title = self.wait_for_element(self.ARTICLE_TITLE_XPATH).text
            content = self.wait_for_element(self.ARTICLE_CONTENT_XPATH).text

            try:
                self.click_element_via_js(self.SEE_MOODS_XPATH)
            except:
                self.click_element_via_js(self.VOTE_DIV_XPATH)
                self.click_element_via_js(self.HAPPY_DIV_XPATH)

            moods = self.collect_moodmeter_data()

            article_data = {
                "title": title,
                "url": self.article_url,
                "content": content,
                "moods": moods,
            }
        except Exception as e:
            logging.error("Failed to scrape article: %s", e)
        finally:
            self.driver.quit()
            logging.info("Finished scraping article.")

        return article_data


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
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="set the logging level",
    )
    return parser.parse_args()


def scrape_article(url):
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    scraper = RapplerScraper(url)
    data = scraper.scrape_article()
    filename = os.path.join("out", f"{url_hash}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f)


if __name__ == "__main__":
    command_line_args = parse_arguments()

    logging.basicConfig(
        level=command_line_args.log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    os.makedirs("out", exist_ok=True)

    sitemap_url = "https://www.rappler.com/sitemap_index.xml"
    sitemap_scraper = SitemapScraper(sitemap_url)
    article_urls = sitemap_scraper.scrape_sitemap(
        max_urls=command_line_args.limit_article,
        ignore_urls=[
            "https://www.rappler.com/latest/",  # Just a list of titles
        ],
    )

    with Pool(processes=cpu_count()) as pool:
        results = pool.map(scrape_article, article_urls)
