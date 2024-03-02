import json
import pprint

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# Setup Chrome options
chrome_options = Options()
chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

# Instantiate the WebDriver with the specified options
driver = webdriver.Chrome(options=chrome_options)


def process_browser_logs_for_network_events(logs):
    """
    Return only logs which have a method that start with "Network.response",
    "Network.request", or "Network.webSocket" since we're interested in the
    network events specifically.
    """
    for entry in logs:
        log = json.loads(entry["message"])["message"]
        if (
            "Network.response" in log["method"]
            or "Network.request" in log["method"]
            or "Network.webSocket" in log["method"]
        ):
            yield log


# Visit the webpage
driver.get("https://www.rkengler.com")

# Retrieve the logs
logs = driver.get_log("performance")

# Process the logs to get only the network events
events = process_browser_logs_for_network_events(logs)

# Write the events to a file
with open("log_entries.txt", "wt") as out:
    for event in events:
        pprint.pprint(event, stream=out)

# Remember to close the driver after use
driver.quit()
