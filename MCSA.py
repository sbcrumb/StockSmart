import os
import sys
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
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

def get_in_stock_interval():
    """Get interval when item is in stock (default 1 hour)"""
    return int(os.getenv("IN_STOCK_INTERVAL", "3600"))

def get_daily_report_hour():
    """Get hour for daily status report (24h format, default 9 = 9am)"""
    return int(os.getenv("DAILY_REPORT_HOUR", "9"))

def get_timezone():
    """Get timezone for daily report (default EST)"""
    return os.getenv("TIMEZONE", "America/New_York")

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

def check_stock(driver, product_url, notified_urls):
    # Set the store cookie
    set_store_cookie(driver, product_url)

    # Get the page source (HTML)
    page_source = driver.page_source

    # Extract product name from URL for notifications
    product_name = product_url.split("/")[-1].replace("-", " ").title()

    # Search for 'inStock': 'True' in the page source
    if "'inStock':'True'" in page_source:
        if product_url not in notified_urls:
            print(f"In Stock: {product_name} (NEW!)")
            send_gotify("Microcenter Stock Alert!", f"{product_name} is now IN STOCK!\n\n{product_url}")
            notified_urls.add(product_url)
        else:
            print(f"In Stock: {product_name} (already notified)")
        return True
    else:
        # Remove from notified set so we can notify again if it comes back
        notified_urls.discard(product_url)
        print(f"Out of Stock: {product_name}")
        return False

def send_daily_report(stock_status):
    """Send daily status report of all monitored items"""
    tz = ZoneInfo(get_timezone())
    now = datetime.now(tz)

    lines = [f"Daily Status Report - {now.strftime('%Y-%m-%d %I:%M %p %Z')}\n"]

    in_stock_count = sum(1 for s in stock_status.values() if s)
    out_of_stock_count = len(stock_status) - in_stock_count

    lines.append(f"In Stock: {in_stock_count} | Out of Stock: {out_of_stock_count}\n")

    for url, is_in_stock in stock_status.items():
        product_name = url.split("/")[-1].replace("-", " ").title()
        status = "IN STOCK" if is_in_stock else "Out of Stock"
        lines.append(f"- {product_name}: {status}")

    message = "\n".join(lines)
    send_gotify("StockSmart Daily Report", message)

def main():
    product_urls = get_product_urls()
    check_interval = get_check_interval()
    in_stock_interval = get_in_stock_interval()
    daily_report_hour = get_daily_report_hour()
    tz = ZoneInfo(get_timezone())

    # Track URLs we've already notified about (to avoid spam)
    notified_urls = set()

    # Track last daily report date
    last_report_date = None

    # Track current stock status for daily report
    stock_status = {}

    print(f"Starting stock checker...")
    print(f"Store ID: {get_store_id()}")
    print(f"Check interval: {check_interval} seconds")
    print(f"In-stock interval: {in_stock_interval} seconds")
    print(f"Daily report: {daily_report_hour}:00 ({get_timezone()})")
    print(f"Monitoring {len(product_urls)} product(s)")
    for url in product_urls:
        print(f"  - {url}")

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
        any_in_stock = False
        for product_url in product_urls:
            is_in_stock = check_stock(driver, product_url, notified_urls)
            stock_status[product_url] = is_in_stock
            if is_in_stock:
                any_in_stock = True

        driver.quit()

        # Check if it's time for daily report
        now = datetime.now(tz)
        today = now.date()
        if now.hour >= daily_report_hour and last_report_date != today:
            print("Sending daily status report...")
            send_daily_report(stock_status)
            last_report_date = today

        # Use longer interval if any item is in stock
        sleep_time = in_stock_interval if any_in_stock else check_interval
        print(f"Sleeping {sleep_time} seconds...")
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()