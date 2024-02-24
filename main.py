from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


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
        """Clicks an element specified by selector using JavaScript execution."""
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
    article_url = "https://www.rappler.com/newsbreak/explainers/how-cory-aquino-cardinal-sin-blocked-charter-change-1997/"
    scraper = RapplerScraper(article_url)
    data = scraper.scrape_article()
    print(data)
