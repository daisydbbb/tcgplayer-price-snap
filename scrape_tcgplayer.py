"""
Scrape the lowest 3 listing prices (price + shipping) for a TCGplayer product,
excluding non-English-language listings.

Requirements:
    pip install selenium

You also need Chrome installed and a matching chromedriver on your PATH
(Selenium 4.6+ can auto-manage the driver for you via Selenium Manager,
so usually `pip install selenium` alone is enough).

Usage:
    python scrape_tcgplayer.py "<tcgplayer product url>"
"""

import re
import sys
from dataclasses import dataclass

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


# TCGplayer doesn't expose a real per-listing language field for every
# product type (sealed product listings, in particular, are all filed under
# the same English SKU no matter what the seller's title says), so the only
# reliable signal is the listing's own title text. Sellers of non-English
# copies conventionally flag it there (e.g. "[KOREAN] ...", "Japanese NM").
NON_ENGLISH_KEYWORDS = [
    "japanese",
    "korean",
    "chinese",
    "german",
    "french",
    "italian",
    "spanish",
    "portuguese",
    "thai",
    "indonesian",
    "russian",
    "polish",
    "vietnamese",
]


@dataclass
class Listing:
    price: float
    shipping: float
    condition: str
    seller: str

    @property
    def total(self) -> float:
        return self.price + self.shipping


def parse_money(text: str) -> float:
    """Turn '$30.00' or '+ $7.00 Shipping' or 'Free Shipping' into a float."""
    if text is None:
        return 0.0
    if "free" in text.lower():
        return 0.0
    match = re.search(r"[\d,]+\.\d{2}", text)
    return float(match.group().replace(",", "")) if match else 0.0


def get_product_name(driver) -> str:
    try:
        el = driver.find_element(By.CSS_SELECTOR, "h1")
        return el.text.strip()
    except Exception:
        return "Unknown product"


def get_number_rarity(driver) -> str:
    """Return e.g. 'OP16-056(SR)' built from the page's Number/Rarity
    attribute rows, or '' if either is missing."""
    number = ""
    rarity = ""
    try:
        rows = driver.find_elements(
            By.CSS_SELECTOR, "ul.product__item-details__attributes > li"
        )
        for row in rows:
            text = row.text.strip()
            if text.startswith("Number:"):
                number = text.split(":", 1)[1].strip()
            elif text.startswith("Rarity:"):
                rarity = text.split(":", 1)[1].strip()
    except Exception:
        pass

    if number and rarity:
        return f"{number}({rarity})"
    return number or rarity


def make_driver(headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,2000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    # Don't block on images/subresources finishing; we only need the DOM.
    options.page_load_strategy = "eager"
    # Skip downloading images entirely (listing rows are all text).
    options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2}
    )
    return webdriver.Chrome(options=options)


def scrape_product(driver, url: str) -> tuple[str, str, list[Listing]]:
    """Scrape one product page with an already-created driver. Returns
    (product_name, number_rarity, listings)."""
    listings: list[Listing] = []

    driver.get(url)

    # Wait for listing rows to render, then for their price fields to
    # actually populate (replaces a blind sleep with a real condition).
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "section.listing-item"))
    )
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".listing-item__listing-data__info__price")
        )
    )

    product_name = get_product_name(driver)
    number_rarity = get_number_rarity(driver)

    rows = driver.find_elements(By.CSS_SELECTOR, "section.listing-item")
    for row in rows:
        row_text = row.text  # fallback for debugging if selectors drift

        # Skip non-English-language listings.
        row_text_lower = row_text.lower()
        if any(kw in row_text_lower for kw in NON_ENGLISH_KEYWORDS):
            continue

        try:
            price_text = row.find_element(
                By.CSS_SELECTOR, ".listing-item__listing-data__info__price"
            ).text
        except Exception:
            continue  # not a real listing row

        try:
            shipping_text = row.find_element(
                By.CSS_SELECTOR, ".listing-item__listing-data__info__shipping-message"
            ).text
        except Exception:
            shipping_text = "Free Shipping"

        try:
            condition_text = row.find_element(
                By.CSS_SELECTOR, ".listing-item__condition"
            ).text
        except Exception:
            condition_text = ""

        try:
            seller_text = row.find_element(
                By.CSS_SELECTOR, ".seller-info__name"
            ).text
        except Exception:
            seller_text = ""

        listings.append(
            Listing(
                price=parse_money(price_text),
                shipping=parse_money(shipping_text),
                condition=condition_text,
                seller=seller_text,
            )
        )

    return product_name, number_rarity, listings


def scrape_listings(url: str, headless: bool = True) -> tuple[str, str, list[Listing]]:
    """Convenience wrapper: launches its own driver for a single URL and
    quits it afterwards. Returns (product_name, number_rarity, listings)."""
    driver = make_driver(headless=headless)
    try:
        return scrape_product(driver, url)
    finally:
        driver.quit()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scrape_tcgplayer.py <tcgplayer_url>")
        sys.exit(1)

    url = sys.argv[1]
    product_name, number_rarity, listings = scrape_listings(url)

    listings.sort(key=lambda l: l.total)
    top3 = listings[:3]

    print(f"Product: {product_name}")
    if number_rarity:
        print(f"Number/Rarity: {number_rarity}")
    print()
    for i, l in enumerate(top3, start=1):
        print(
            f"{i}. Total: ${l.total:.2f}  "
            f"(price ${l.price:.2f} + shipping ${l.shipping:.2f})  "
            f"[{l.condition}]  seller: {l.seller}"
        )


if __name__ == "__main__":
    main()
