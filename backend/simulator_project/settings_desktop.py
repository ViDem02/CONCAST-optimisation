import os
from pathlib import Path

# Pre-set env defaults so base settings import won't fail
_BASE_DIR = Path(__file__).resolve().parent.parent
os.environ.setdefault('MEDIA_ROOT', str(_BASE_DIR / 'media'))
os.environ.setdefault('STATIC_ROOT', str(_BASE_DIR / 'static'))
os.environ.setdefault('SESSION_EXPIRE_AT_BROWSER_CLOSE', 'False')
os.environ.setdefault('IS_DOCKER', '0')
os.environ.setdefault('DJANGO_SECRET_KEY', 'sparc-desktop-secret-key')

from .settings import *  # noqa

# Desktop overrides: use SQLite DB local to backend folder
DESKTOP_DB_NAME = os.environ.get('SPARC_SQLITE_PATH', str(BASE_DIR / 'desktop_db.sqlite3'))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DESKTOP_DB_NAME,
    }
}

# Allow local app hostnames
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost 127.0.0.1').split()

# Default to False unless explicitly set; you can flip to True for dev
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# Static files in desktop context (served by Django if needed)
STATIC_URL = '/static/'
STATIC_ROOT = os.environ.get('STATIC_ROOT', str(BASE_DIR / 'static'))

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.environ.get('MEDIA_ROOT', str(BASE_DIR / 'media'))

SESSION_EXPIRE_AT_BROWSER_CLOSE = os.environ.get('SESSION_EXPIRE_AT_BROWSER_CLOSE', 'False') == 'True'