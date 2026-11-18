import os

DATABASE_URL = os.environ["DATABASE_URL"]

NTFY_URL = os.environ.get("NTFY_URL", "")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "geniscent")

PUBLIC_URL = os.environ.get("PUBLIC_URL", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"
TIMEZONE = "Europe/Berlin"

USER_AGENT = "MarketTrends/0.1"
REQUEST_GAP_SECONDS = 5

SNAPSHOT_DIR = os.environ.get("SNAPSHOT_DIR", "/data/snapshots")
MIN_GAP_SECONDS = 5
