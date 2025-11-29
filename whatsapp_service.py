"""
WhatsApp Business API Integration for OTP Sending

This module handles sending OTP messages via WhatsApp Business API.
Configure the following environment variables in .env:

WHATSAPP_API_URL=https://graph.facebook.com/v18.0/<PHONE_NUMBER_ID>/messages
WHATSAPP_ACCESS_TOKEN=your_whatsapp_business_api_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_OTP_TEMPLATE_NAME=otp_template
WHATSAPP_OTP_TEMPLATE_LANGUAGE=en
"""

import os
import httpx
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# WhatsApp Business API Configuration
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_OTP_TEMPLATE_NAME = os.getenv("WHATSAPP_OTP_TEMPLATE_NAME", "otp_verification")
WHATSAPP_OTP_TEMPLATE_LANGUAGE = os.getenv("WHATSAPP_OTP_TEMPLATE_LANGUAGE", "en")


def is_whatsapp_configured() -> bool:
    """Check if WhatsApp API is configured"""
    return bool(WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID)


async def send_otp_via_whatsapp(phone_number: str, otp: str) -> dict:
    """
    Send OTP via WhatsApp Business API
    
    Args:
        phone_number: Recipient's phone number (without country code, will add +91)
        otp: The 6-digit OTP to send
        
    Returns:
        dict: Response containing success status and message
    """
    if not is_whatsapp_configured():
        logger.warning("WhatsApp API not configured. OTP not sent via WhatsApp.")
        return {
            "success": False,
            "message": "WhatsApp API not configured",
            "otp_logged": True
        }
    
    # Format phone number with country code (India +91)
    # Remove any leading zeros or spaces
    clean_phone = phone_number.strip().lstrip('0')
    if not clean_phone.startswith('91'):
        clean_phone = f"91{clean_phone}"
    
    # Build API URL
    api_url = WHATSAPP_API_URL or f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Message payload using template
    # Templates must be pre-approved by WhatsApp
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "template",
        "template": {
            "name": WHATSAPP_OTP_TEMPLATE_NAME,
            "language": {
                "code": WHATSAPP_OTP_TEMPLATE_LANGUAGE
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": otp
                        }
                    ]
                },
                # If your template has a button with OTP autofill
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [
                        {
                            "type": "text",
                            "text": otp
                        }
                    ]
                }
            ]
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, headers=headers, json=payload)
            response_data = response.json()
            
            if response.status_code == 200:
                logger.info(f"WhatsApp OTP sent successfully to {phone_number}")
                return {
                    "success": True,
                    "message": "OTP sent via WhatsApp",
                    "message_id": response_data.get("messages", [{}])[0].get("id")
                }
            else:
                logger.error(f"WhatsApp API error: {response_data}")
                return {
                    "success": False,
                    "message": f"WhatsApp API error: {response_data.get('error', {}).get('message', 'Unknown error')}",
                    "error_code": response_data.get('error', {}).get('code')
                }
                
    except httpx.TimeoutException:
        logger.error("WhatsApp API request timed out")
        return {
            "success": False,
            "message": "WhatsApp API request timed out"
        }
    except Exception as e:
        logger.error(f"Error sending WhatsApp OTP: {str(e)}")
        return {
            "success": False,
            "message": f"Error sending WhatsApp OTP: {str(e)}"
        }


async def send_otp_via_whatsapp_text(phone_number: str, otp: str) -> dict:
    """
    Send OTP via WhatsApp as a simple text message (if templates are not set up)
    Note: This may not work in production as WhatsApp Business API requires templates for business-initiated messages
    
    Args:
        phone_number: Recipient's phone number
        otp: The 6-digit OTP to send
        
    Returns:
        dict: Response containing success status and message
    """
    if not is_whatsapp_configured():
        logger.warning("WhatsApp API not configured. OTP not sent via WhatsApp.")
        return {
            "success": False,
            "message": "WhatsApp API not configured",
            "otp_logged": True
        }
    
    # Format phone number with country code (India +91)
    clean_phone = phone_number.strip().lstrip('0')
    if not clean_phone.startswith('91'):
        clean_phone = f"91{clean_phone}"
    
    api_url = WHATSAPP_API_URL or f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Simple text message payload
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": f"Your Vaidya Health OTP is: {otp}\n\nThis OTP is valid for 10 minutes. Do not share it with anyone."
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, headers=headers, json=payload)
            response_data = response.json()
            
            if response.status_code == 200:
                logger.info(f"WhatsApp text OTP sent successfully to {phone_number}")
                return {
                    "success": True,
                    "message": "OTP sent via WhatsApp",
                    "message_id": response_data.get("messages", [{}])[0].get("id")
                }
            else:
                logger.error(f"WhatsApp API error: {response_data}")
                return {
                    "success": False,
                    "message": f"WhatsApp API error: {response_data.get('error', {}).get('message', 'Unknown error')}",
                    "error_code": response_data.get('error', {}).get('code')
                }
                
    except Exception as e:
        logger.error(f"Error sending WhatsApp OTP: {str(e)}")
        return {
            "success": False,
            "message": f"Error sending WhatsApp OTP: {str(e)}"
        }
