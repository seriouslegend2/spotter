import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "assessment-local-only-secret-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if host.strip()]
ROOT_URLCONF = "spotter_api.urls"
INSTALLED_APPS = []
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
TEMPLATES = []
WSGI_APPLICATION = "spotter_api.wsgi.application"
DEFAULT_CHARSET = "utf-8"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "TIMEOUT": 3600}}
