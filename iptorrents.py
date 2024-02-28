import os
import time
import requests
import re
from selectolax.parser import HTMLParser
from prometheus_client import start_http_server, Gauge


EXPORTER_PORT = int(os.getenv("EXPORTER_PORT", 17500))
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", 1800))

# Environment variable containing the cookie string
COOKIE_STRING = os.getenv("COOKIE_STRING")
URL = os.getenv("PROFILE_URL")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15"

# Prometheus metrics
UPLOAD_METRIC = Gauge("upload_value_bytes", "Value extracted from the webpage in bytes")
DOWNLOAD_METRIC = Gauge(
    "download_value_bytes", "Value extracted from the webpage in bytes"
)


def convert_to_bytes(value_str):
    # Regular expression to extract the value within parentheses
    match = re.search(r"\(([\d,]+)\s*(\w+)\)", value_str)
    if match:
        size, unit = match.groups()
        size = size.replace(",", "")  # Remove commas from the number
        size_bytes = float(size)
        if unit == "GB":
            size_bytes *= 1024 * 1024 * 1024
        elif unit == "MB":
            size_bytes *= 1024 * 1024
        elif unit == "KB":
            size_bytes *= 1024
        elif unit == "B":
            size_bytes *= 1
        return size_bytes
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
                "#body > tbody > tr > td > center > center > table > tbody > tr:nth-child(7) > td"
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
                "#body > tbody > tr > td > center > center > table > tbody > tr:nth-child(8) > td"
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
