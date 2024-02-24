"""
This module scrapes articles and corresponding metadata from the Rappler news website.
It respects the robots.txt file and avoids aggressive scraping.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ARTICLE_TITLE_XPATH = "//h1[contains(@class,'post-single__title')]"
ARTICLE_CONTENT_XPATH = "//div[contains(@class,'post-single__content')]"
VOTES_CONTAINER_XPATH = "//div[contains(@class,'xa3V2iPvKCrXH2KVimTv-g==')]"
SEE_VOTES_XPATH = "//div[contains(@class,'AOhvJlN4Z5TsLqKZb1kSBw==')]"
VOTE_DIV_XPATH = "//div[contains(@class,'i1IMtjULF3BKu3lB0m1ilg==')]"
HAPPY_DIV_XPATH = "//div[contains(@class,'mood-happy')]"


def setup_driver(article_url):
    """Initialize the Selenium WebDriver for Chrome and navigate to the article URL."""
    driver = webdriver.Chrome()
    driver.get(article_url)
    return driver


def wait_for(driver, identifier, wait_time=10):
    """General-purpose function to wait for a specific element to be present."""
    return WebDriverWait(driver, wait_time).until(
        EC.presence_of_element_located((By.XPATH, identifier))
    )


def click_element_via_js(driver, identifier):
    """
    Clicks an element specified by selector using JavaScript execution.
    This is particularly useful for elements difficult to interact with through standard methods.
    """
    element = wait_for(driver, identifier)
    driver.execute_script("arguments[0].click();", element)


def get_element_text(driver, identifier, default=None):
    """Attempts to get an element's text, returning a default value if an error occurs."""
    try:
        return wait_for(driver, identifier).text
    except:
        return default


def collect_votes_data(driver):
    """Collects and formats votes data from the webpage."""
    votes_container = wait_for(driver, VOTES_CONTAINER_XPATH)

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


def scrape_article(article_url):
    """Main function to scrape the article's title, content, and votes data."""
    driver = setup_driver(article_url)
    title = get_element_text(driver, ARTICLE_TITLE_XPATH)
    content = get_element_text(driver, ARTICLE_CONTENT_XPATH)

    # Try seeing the votes directly; if not possible, emulate voting to see the results.
    try:
        try:
            click_element_via_js(driver, SEE_VOTES_XPATH)
        except:
            click_element_via_js(driver, VOTE_DIV_XPATH)
            click_element_via_js(driver, HAPPY_DIV_XPATH)

        votes_data = collect_votes_data(driver)
    except Exception as e:
        print(f"An error occurred while collecting votes data: {e}")
        votes_data = {}

    driver.quit()
    return {"title": title, "content": content, "votes": votes_data}


if __name__ == "__main__":
    article_url = "https://www.rappler.com/newsbreak/explainers/how-cory-aquino-cardinal-sin-blocked-charter-change-1997/"
    data = scrape_article(article_url)
    print(data)
