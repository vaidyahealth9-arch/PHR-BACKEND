"""
Firebase Authentication Service for VaidyaOne.
Handles initialization of Firebase Admin SDK and verification of client ID tokens.
"""

import os
import logging
import firebase_admin
from firebase_admin import credentials, auth

logger = logging.getLogger(__name__)

# Track if initialization was successful
_firebase_initialized = False

try:
    # Attempt to initialize using Application Default Credentials (ADC) or env settings.
    # On Google Cloud (e.g. Cloud Run), this automatically picks up the service account.
    firebase_admin.initialize_app()
    _firebase_initialized = True
    logger.info("Firebase Admin SDK successfully initialized using Application Default Credentials (ADC).")
except ValueError:
    # App is already initialized (e.g., during tests or hot reload)
    _firebase_initialized = True
except Exception as e:
    logger.warning(f"Could not initialize Firebase Admin SDK via ADC: {e}")
    # Fallback to local service account file if environment variable is provided
    cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY", "")
    if cred_path and os.path.exists(cred_path):
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info(f"Firebase Admin SDK initialized using credential file: {cred_path}")
        except Exception as cert_err:
            logger.error(f"Failed to initialize Firebase Admin SDK using credential file {cred_path}: {cert_err}")
    else:
        logger.warning(
            "Firebase Admin SDK is not initialized. Firebase OTP token verification will fail. "
            "Please check that GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_SERVICE_ACCOUNT_KEY is configured."
        )


def verify_firebase_id_token(id_token: str) -> dict | None:
    """
    Verifies a Firebase ID token sent by the client.
    
    Args:
        id_token: The Firebase JWT token string.
        
    Returns:
        dict: The decoded token payload if valid, otherwise None.
    """
    if not _firebase_initialized:
        logger.error("Attempted to verify Firebase ID token, but Firebase Admin SDK is not initialized.")
        return None
        
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        logger.error(f"Firebase ID token verification failed: {e}")
        return None
