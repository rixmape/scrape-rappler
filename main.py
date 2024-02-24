"""
This module scrapes the articles and corresponding metadata from the Rappler
news website. It honors the robots.txt file and does not scrape the website
aggressively.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def initialize_driver(article_url):
    """Initialize the selenium webdriver and navigate to the article URL."""
    driver = webdriver.Chrome()
    driver.get(article_url)
    return driver


def wait_for_element(driver, xpath, wait_time=10):
    """Wait for an element to be present and return it."""
    return WebDriverWait(driver, wait_time).until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )


def click_element(driver, element):
    """Execute a script to click on a specified element."""
    driver.execute_script("arguments[0].click();", element)


def collect_votes_data(driver):
    """Collects and returns the votes data in a dictionary format."""
    votes_container = wait_for_element(
        driver,
        "//div[contains(@class,'xa3V2iPvKCrXH2KVimTv-g==')]",
    )

    spans = votes_container.find_elements(By.TAG_NAME, "span")
    votes = [span.text for span in spans if "%" in span.text]

    headings = votes_container.find_elements(By.TAG_NAME, "h4")
    moods = [heading.text for heading in headings]

    return dict(zip(moods, votes))


def scrape_article(article_url):
    """Scrape the article for votes data."""
    driver = initialize_driver(article_url)

    try:
        # Attempt to directly access votes, if fails, try to cast a vote.
        try:
            see_votes = wait_for_element(
                driver,
                "//div[contains(@class,'AOhvJlN4Z5TsLqKZb1kSBw==')]",
            )
            click_element(driver, see_votes)
        except:
            vote_div = wait_for_element(
                driver,
                "//div[contains(@class,'i1IMtjULF3BKu3lB0m1ilg==')]",
            )
            click_element(driver, vote_div)

            happy_div = wait_for_element(
                driver,
                "//div[contains(@class,'mood-happy')]",
            )
            click_element(driver, happy_div)

        return collect_votes_data(driver)
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    article_url = "https://www.rappler.com/newsbreak/explainers/how-cory-aquino-cardinal-sin-blocked-charter-change-1997/"
    data = scrape_article(article_url)
    print(data)
