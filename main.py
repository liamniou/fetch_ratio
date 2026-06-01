import json
import logging
import os
import re
import time

import requests
from bs4 import BeautifulSoup
from prometheus_client import start_http_server, Gauge

# ── Configuration ────────────────────────────────────────────────────
# SITES_CONFIG is a JSON array of site objects, each with:
#   name, profile_url, cookie_string, user_agent, dl_selector, ul_selector
#
# For backward-compat, fall back to the legacy single-site env vars.

SITES_CONFIG_RAW = os.getenv("SITES_CONFIG")
if SITES_CONFIG_RAW:
    SITES = json.loads(SITES_CONFIG_RAW)
else:
    SITES = [
        {
            "name": os.getenv("PROFILE_URL", "default"),
            "profile_url": os.getenv("PROFILE_URL"),
            "cookie_string": os.getenv("COOKIE_STRING"),
            "user_agent": os.getenv(
                "USER_AGENT",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36",
            ),
            "dl_selector": os.getenv("DL_ELEMENT_SELECTOR"),
            "ul_selector": os.getenv("UL_ELEMENT_SELECTOR"),
        }
    ]

EXPORTER_PORT = int(os.getenv("EXPORTER_PORT", 17500))
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL", 3600))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", 30))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 30))

# Notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# ── Prometheus metrics (labelled by site) ────────────────────────────
UPLOAD_METRIC = Gauge(
    "upload_value_bytes",
    "Upload value extracted from the webpage in bytes",
    ["site"],
)
DOWNLOAD_METRIC = Gauge(
    "download_value_bytes",
    "Download value extracted from the webpage in bytes",
    ["site"],
)

UNIT_MULTIPLIERS = {
    "B": 1,
    "KB": 1024,
    "KIB": 1024,
    "MB": 1024**2,
    "MIB": 1024**2,
    "GB": 1024**3,
    "GIB": 1024**3,
    "TB": 1024**4,
    "TIB": 1024**4,
}


def convert_to_bytes(value_str):
    """Convert a human-readable size string (e.g. '1.23 GiB') to bytes."""
    cleaned = (
        value_str.replace("\n", "")
        .replace("\r", "")
        .replace(",", "")
        .replace("\xa0", "")  # non-breaking space
        .strip()
    )
    # Strip any leading text (e.g. "Downloaded", "Uploaded:", "UP: ", etc.)
    # Keep only the numeric value + unit at the end
    match = re.search(r"([\d.]+)\s*([A-Za-z]+)\s*$", cleaned)
    if not match:
        return None
    value, unit = match.groups()
    multiplier = UNIT_MULTIPLIERS.get(unit.upper())
    if multiplier is None:
        return None
    return float(value) * multiplier


# ── Notifications ────────────────────────────────────────────────────
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code != 200:
            logging.error(f"Failed to send Telegram message: {response.text}")
    except Exception as e:
        logging.error(f"Error sending Telegram message: {e}")


def send_discord_message(message):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        payload = {"content": message}
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
        if response.status_code not in (200, 204):
            logging.error(f"Failed to send Discord message: {response.text}")
    except Exception as e:
        logging.error(f"Error sending Discord message: {e}")


def send_notification(message):
    """Send a notification to all configured channels."""
    send_telegram_message(message)
    send_discord_message(message)


# ── Scraping ─────────────────────────────────────────────────────────
def fetch_page(profile_url, cookie_string, user_agent):
    """Fetch the profile page HTML using cookie-based auth."""
    headers = {
        "User-Agent": user_agent,
        "Cookie": cookie_string,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    response = requests.get(
        profile_url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True
    )
    response.raise_for_status()
    return response.text


def extract_value(html, css_selector):
    """Extract text content from an HTML element matching the CSS selector."""
    soup = BeautifulSoup(html, "lxml")
    element = soup.select_one(css_selector)
    if element is None:
        return None
    return element.get_text(strip=True)


def fetch_site_data(site):
    """Fetch DL/UL data for a single site, with retries."""
    site_name = site["name"]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info(f"[{site_name}] Fetching {site['profile_url']} (attempt {attempt})")
            html = fetch_page(
                site["profile_url"], site["cookie_string"], site["user_agent"]
            )

            # Handle empty selectors as fixed 0 value
            dl_selector = site.get("dl_selector", "")
            ul_selector = site.get("ul_selector", "")

            if dl_selector:
                dl_raw = extract_value(html, dl_selector)
                if dl_raw is None:
                    raise ValueError(f"Download element not found with selector: {dl_selector}")
                dl_value_index = site.get("dl_value_index")
                if dl_value_index is not None and "/" in dl_raw:
                    dl_raw = dl_raw.split("/")[dl_value_index].strip()
                dl = convert_to_bytes(dl_raw)
                if dl is None:
                    raise ValueError(f"Could not parse DL value — raw='{dl_raw}'")
            else:
                dl_raw = "0"
                dl = 0.0

            if ul_selector:
                ul_raw = extract_value(html, ul_selector)
                if ul_raw is None:
                    raise ValueError(f"Upload element not found with selector: {ul_selector}")
                ul_value_index = site.get("ul_value_index")
                if ul_value_index is not None and "/" in ul_raw:
                    ul_raw = ul_raw.split("/")[ul_value_index].strip()
                ul = convert_to_bytes(ul_raw)
                if ul is None:
                    raise ValueError(f"Could not parse UL value — raw='{ul_raw}'")
            else:
                ul_raw = "0"
                ul = 0.0

            logging.info(f"[{site_name}] DL={dl} (raw='{dl_raw}'), UL={ul} (raw='{ul_raw}')")

            return dl, ul

        except Exception as e:
            logging.error(f"[{site_name}] Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                send_notification(
                    f"❌ Failed to fetch data for {site_name} "
                    f"({site['profile_url']}) after {MAX_RETRIES} attempts: {e}"
                )
                return None, None


# ── Main loop ────────────────────────────────────────────────────────
if __name__ == "__main__":
    start_http_server(EXPORTER_PORT)
    logging.info(
        f"Exporter started on :{EXPORTER_PORT}, "
        f"monitoring {len(SITES)} site(s), interval={FETCH_INTERVAL}s"
    )

    while True:
        for site in SITES:
            label = site["name"]
            dl, ul = fetch_site_data(site)
            if dl is not None and ul is not None:
                DOWNLOAD_METRIC.labels(site=label).set(dl)
                UPLOAD_METRIC.labels(site=label).set(ul)

        time.sleep(FETCH_INTERVAL)
