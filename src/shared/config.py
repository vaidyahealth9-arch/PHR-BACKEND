"""Centralized config for PHR backend (FastAPI)
Read from environment variables. Safe defaults kept minimal.
This module is intentionally passive; import and use in other modules as needed.
"""
import os

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5433/phr')
SECRET_KEY = os.getenv('SECRET_KEY', 'replace-with-a-long-random-secret')
RUN_SEED_DATA = os.getenv('RUN_SEED_DATA', 'false').lower() in ('1', 'true', 'yes')
LIMS_BASE_URL = os.getenv('LIMS_BASE_URL', 'http://localhost:8080')

# Token defaults
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '15'))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', '7'))

# WhatsApp / integrations (optional)
WHATSAPP_API_URL = os.getenv('WHATSAPP_API_URL', '')
WHATSAPP_ACCESS_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN', '')

config = {
    'DATABASE_URL': DATABASE_URL,
    'SECRET_KEY': SECRET_KEY,
    'RUN_SEED_DATA': RUN_SEED_DATA,
    'LIMS_BASE_URL': LIMS_BASE_URL,
}
