FROM python:3.11-slim

# Install Google Chrome (stable) so Selenium has a real browser to drive.
# Selenium 4.6+'s built-in Selenium Manager will auto-download a matching
# chromedriver at runtime, so we don't need to install one separately.
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget \
        gnupg \
        curl \
        unzip \
    && wget -q -O /tmp/google-chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Render sets $PORT at runtime; gunicorn's timeout is bumped up since a
# scrape (especially batch mode) can take longer than the 30s default.
CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120
