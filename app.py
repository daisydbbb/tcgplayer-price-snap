"""
Simple web UI for scrape_tcgplayer.py.

Requirements:
    pip install flask selenium pandas openpyxl

Usage:
    python3 app.py
    # then open http://127.0.0.1:5000 in a browser
"""

import io
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file
from selenium.common.exceptions import TimeoutException, WebDriverException
from werkzeug.utils import secure_filename

from scrape_tcgplayer import make_driver, scrape_listings, scrape_product

app = Flask(__name__)

BATCH_OUTPUT_COLUMNS = ["Full Name", "Number", "Price1", "Price2", "Price3", "Time"]
MAX_BATCH_ROWS = 200


def validate_tcgplayer_url(url: str) -> str | None:
    """Return an error message if the URL is invalid, else None."""
    if not url or not url.strip():
        return "Please paste a TCGplayer product link."

    url = url.strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return "That doesn't look like a valid URL."

    if parsed.scheme not in ("http", "https"):
        return "Link must start with http:// or https://."
    if not parsed.netloc.lower().endswith("tcgplayer.com"):
        return "That's not a tcgplayer.com link."
    if not parsed.path.startswith("/product/"):
        return "That's not a TCGplayer product page link (expected .../product/...)."

    return None


def find_column(df: pd.DataFrame, name: str) -> str | None:
    """Case-insensitive column lookup; returns the actual column name."""
    target = name.strip().lower()
    for col in df.columns:
        if str(col).strip().lower() == target:
            return col
    return None


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    error = validate_tcgplayer_url(url)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    try:
        product_name, number_rarity, listings = scrape_listings(url)
    except TimeoutException:
        return jsonify(
            {
                "ok": False,
                "error": "Timed out waiting for listings to load. The link may be "
                "wrong, the product may have no listings, or TCGplayer's page "
                "layout may have changed.",
            }
        ), 502
    except WebDriverException as exc:
        return jsonify(
            {"ok": False, "error": f"Browser automation error: {exc.msg or exc}"}
        ), 502

    if not listings:
        return jsonify(
            {
                "ok": False,
                "error": f'No listings found for "{product_name}". '
                "The product may be out of stock or the link may be incorrect.",
            }
        ), 404

    listings.sort(key=lambda l: l.total)
    top3 = listings[:3]

    lines = [f"Product: {product_name}"]
    if number_rarity:
        lines.append(f"Number/Rarity: {number_rarity}")
    lines.append("")
    for i, l in enumerate(top3, start=1):
        lines.append(
            f"{i}. Total: ${l.total:.2f}  "
            f"(price ${l.price:.2f} + shipping ${l.shipping:.2f})  "
            f"[{l.condition}]  seller: {l.seller}"
        )

    return jsonify({"ok": True, "text": "\n".join(lines)})


@app.route("/api/batch", methods=["POST"])
def api_batch():
    file = request.files.get("file")
    if file is None or file.filename == "":
        return jsonify(
            {"ok": False, "error": "Please choose a CSV or Excel file to upload."}
        ), 400

    filename = file.filename
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("csv", "xlsx"):
        return jsonify(
            {"ok": False, "error": "Please upload a .csv or .xlsx file."}
        ), 400

    try:
        if ext == "csv":
            df = pd.read_csv(file, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(
                file, dtype=str, keep_default_na=False, engine="openpyxl"
            )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Could not read the file: {exc}"}), 400

    if df.empty:
        return jsonify({"ok": False, "error": "The file has no rows."}), 400

    if len(df) > MAX_BATCH_ROWS:
        return jsonify(
            {
                "ok": False,
                "error": f"That's {len(df)} rows; please limit uploads to "
                f"{MAX_BATCH_ROWS} at a time.",
            }
        ), 400

    link_col = find_column(df, "link")
    if link_col is None:
        if len(df.columns) >= 2:
            link_col = df.columns[1]  # fall back to Column B
        else:
            return jsonify(
                {"ok": False, "error": "Couldn't find a 'Link' column in the file."}
            ), 400

    # Make sure every output column exists, creating any that are missing.
    col_map = {}
    for name in BATCH_OUTPUT_COLUMNS:
        existing = find_column(df, name)
        if existing is None:
            df[name] = ""
            col_map[name] = name
        else:
            col_map[name] = existing

    def write_row(idx, full_name, number_rarity, prices, timestamp):
        df.at[idx, col_map["Full Name"]] = full_name
        df.at[idx, col_map["Number"]] = number_rarity
        for i in range(3):
            df.at[idx, col_map[f"Price{i + 1}"]] = prices[i] if i < len(prices) else ""
        df.at[idx, col_map["Time"]] = timestamp

    driver = make_driver(headless=True)
    try:
        for idx in df.index:
            url = str(df.at[idx, link_col] or "").strip()

            error = validate_tcgplayer_url(url)
            if error:
                write_row(idx, f"ERROR: {error}", "", [], now_str())
                continue

            try:
                product_name, number_rarity, listings = scrape_product(driver, url)
            except TimeoutException:
                write_row(
                    idx,
                    "ERROR: timed out waiting for listings to load",
                    "",
                    [],
                    now_str(),
                )
                continue
            except WebDriverException as exc:
                write_row(
                    idx, f"ERROR: browser error ({exc.msg or exc})", "", [], now_str()
                )
                continue

            if not listings:
                write_row(idx, f"{product_name} (no listings found)", number_rarity, [], now_str())
                continue

            listings.sort(key=lambda l: l.total)
            prices = [f"{l.total:.2f}" for l in listings[:3]]
            write_row(idx, product_name, number_rarity, prices, now_str())
    finally:
        driver.quit()

    buffer = io.BytesIO()
    out_name = f"snapped_{secure_filename(filename)}"
    if ext == "csv":
        df.to_csv(buffer, index=False)
        mimetype = "text/csv"
    else:
        df.to_excel(buffer, index=False, engine="openpyxl")
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    buffer.seek(0)

    return send_file(
        buffer, mimetype=mimetype, as_attachment=True, download_name=out_name
    )


if __name__ == "__main__":
    # Port 5000 is claimed by macOS Control Center (AirPlay Receiver) by
    # default, which can conflict with local dev servers, so use 5001.
    app.run(debug=True, port=5001)
