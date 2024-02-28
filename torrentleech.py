import os
import time
import requests
import re
from selectolax.parser import HTMLParser
from prometheus_client import start_http_server, Gauge


EXPORTER_PORT = int(os.getenv("EXPORTER_PORT", 17500))
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", 1800))

# Environment variable containing the cookie string
COOKIE_STRING = os.getenv(
    "COOKIE_STRING",
)
URL = os.getenv("PROFILE_URL")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15"

# Prometheus metrics
UPLOAD_METRIC = Gauge("upload_value_bytes", "Value extracted from the webpage in bytes")
DOWNLOAD_METRIC = Gauge(
    "download_value_bytes", "Value extracted from the webpage in bytes"
)


def convert_to_bytes(value_str):
    # Regular expression to extract numeric value and unit
    match = re.match(r"^([\d.]+)\s*(\w+)$", value_str)
    if match:
        value, unit = match.groups()
        value = float(value)
        if unit == "B":
            return value
        elif unit == "KB":
            return value * 1024
        elif unit == "MB":
            return value * 1024 * 1024
        elif unit == "GB":
            return value * 1024 * 1024 * 1024
        elif unit == "TB":
            return value * 1024 * 1024 * 1024 * 1024
    return None


def fetch_value():
    try:
        # Fetch the webpage
        response = requests.get(
            URL, headers={"Cookie": COOKIE_STRING, "User-Agent": USER_AGENT}
        )

        if response.status_code == 200:
            # Parse the HTML
            tree = HTMLParser(response.text)
            upload_element = tree.css_first(
                "body > div.mt-20.tl-content.tl-lights-off.has-support-msg > div > div > div > div.user-profile-container > div > div > div > table > tbody > tr:nth-child(1) > td:nth-child(2) > div.profile-info > div.profile-uploaded > span"
            )
            if upload_element:
                upload_text = upload_element.text()
                upload_bytes = convert_to_bytes(upload_text)
                if upload_bytes is not None:
                    UPLOAD_METRIC.set(upload_bytes)
                else:
                    print("Invalid format for upload:", upload_text)
            else:
                print("Upload element not found")

            # Extract download value
            download_element = tree.css_first(
                "body > div.mt-20.tl-content.tl-lights-off.has-support-msg > div > div > div > div.user-profile-container > div > div > div > table > tbody > tr:nth-child(1) > td:nth-child(2) > div.profile-info > div.profile-downloaded > span"
            )
            if download_element:
                download_text = download_element.text()
                download_bytes = convert_to_bytes(download_text)
                if download_bytes is not None:
                    DOWNLOAD_METRIC.set(download_bytes)
                else:
                    print("Invalid format for download:", download_text)
            else:
                print("Download element not found")
        else:
            print("Failed to fetch webpage:", response.status_code)
    except Exception as e:
        print("Error fetching webpage:", str(e))


if __name__ == "__main__":
    start_http_server(EXPORTER_PORT)

    while True:
        fetch_value()
        time.sleep(FETCH_INTERVAL)
