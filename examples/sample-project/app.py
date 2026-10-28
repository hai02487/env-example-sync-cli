import os

API_KEY = os.environ["API_KEY"]
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
TIMEOUT = int(os.getenv("TIMEOUT", "30"))
