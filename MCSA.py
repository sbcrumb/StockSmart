import os
import sys
import time
import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables (works for both local dev and Docker)
load_dotenv()

def get_product_urls():
    """Get product URLs from environment variable (comma-separated)"""
    urls = os.getenv("PRODUCT_URLS", "")
    if not urls:
        print("ERROR: No PRODUCT_URLS configured in environment")
        sys.exit(1)
    return [url.strip() for url in urls.split(",") if url.strip()]

def get_store_id():
    """Get Microcenter store ID from environment variable"""
    return os.getenv("STORE_ID", "051")

def get_check_interval():
    """Get check interval in seconds from environment variable"""
    return int(os.getenv("CHECK_INTERVAL", "300"))

def send_gotify(title, message):
    try:
        gotify_url = os.getenv("GOTIFY_URL")
        gotify_token = os.getenv("GOTIFY_TOKEN")

        if not gotify_url or not gotify_token:
            print("Gotify not configured, skipping notification")
            return

        response = requests.post(
            f"{gotify_url}/message",
            params={"token": gotify_token},
            json={
                "title": title,
                "message": message,
                "priority": 8
            }
        )
        response.raise_for_status()
        print("Gotify notification sent!")
    except Exception as e:
        print(f"Failed to send Gotify notification: {e}")

def set_store_cookie(driver, product_url):
    # Get the main store page URL so you don't overload the product webpage. Selenium limitation
    driver.get("https://www.microcenter.com")

    # Wait for the page to load, adjust as needed (seconds)
    time.sleep(0)

    # Set the storeSelected cookie
    driver.add_cookie({
        'name': 'storeSelected',
        'value': get_store_id(),
        'domain': '.microcenter.com',
        'path': '/',
        'secure': True,
        'httpOnly': False
    })
    # Get the product page URL
    driver.get(product_url)

    # Wait for the page to load, adjust as needed (seconds)
    time.sleep(0)

def check_stock(driver, product_url):
    # Set the store cookie
    set_store_cookie(driver, product_url)

    # Get the page source (HTML)
    page_source = driver.page_source

    # Extract product name from URL for notifications
    product_name = product_url.split("/")[-1].replace("-", " ").title()

    # Search for 'inStock': 'True' in the page source
    if "'inStock':'True'" in page_source:
        print(f"In Stock: {product_name}")
        send_gotify("Microcenter Stock Alert!", f"{product_name} is now IN STOCK!\n\n{product_url}")
        return True
    else:
        print(f"Out of Stock: {product_name}")
        return False

def main():
    product_urls = get_product_urls()
    check_interval = get_check_interval()

    print(f"Starting stock checker...")
    print(f"Store ID: {get_store_id()}")
    print(f"Check interval: {check_interval} seconds")
    print(f"Monitoring {len(product_urls)} product(s)")

    while True:
        # Set up Chrome options to enable headless mode
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Set up the WebDriver with the specified options
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

        # Check stock for each product URL
        found_in_stock = False
        for product_url in product_urls:
            if check_stock(driver, product_url):
                found_in_stock = True

        driver.quit()

        if found_in_stock:
            print("Item(s) found in stock! Exiting...")
            sys.exit()

        time.sleep(check_interval)

if __name__ == "__main__":
    main()