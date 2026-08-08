import os
import logging
import urllib.request
import json
import re

logger = logging.getLogger(__name__)

def send_sms_otp(phone_number: str, otp: str) -> bool:
    """
    Dispatches a real SMS to the given phone number with the 6-digit OTP code.
    Supports Fast2SMS (India), Twilio (Global), and custom HTTP SMS gateways.
    """
    digits = re.sub(r'\D', '', str(phone_number))
    formatted_phone = digits[-10:] if len(digits) >= 10 else digits
    
    # 1. Fast2SMS Integration (Fast, reliable SMS delivery for Indian mobile numbers)
    fast2sms_api_key = os.getenv("FAST2SMS_API_KEY", "")
    if fast2sms_api_key:
        try:
            url = "https://www.fast2sms.com/dev/bulkV2"
            payload = {
                "variables_values": otp,
                "route": "otp",
                "numbers": formatted_phone
            }
            headers = {
                "authorization": fast2sms_api_key,
                "Content-Type": "application/json"
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode())
                logger.info(f"[FAST2SMS GATEWAY] Sent OTP {otp} to +91{formatted_phone}: {result}")
                return True
        except Exception as e:
            logger.error(f"[FAST2SMS GATEWAY ERROR] Failed to send SMS: {e}")

    # 2. Twilio Integration
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_PHONE_NUMBER", "")
    if account_sid and auth_token and from_number:
        try:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            message = client.messages.create(
                body=f"Your VaidyaOne OTP code is: {otp}",
                from_=from_number,
                to=f"+91{formatted_phone}"
            )
            logger.info(f"[TWILIO GATEWAY] Sent OTP {otp} to +91{formatted_phone}, SID: {message.sid}")
            return True
        except Exception as e:
            logger.error(f"[TWILIO GATEWAY ERROR] Failed to send SMS: {e}")

    logger.info(f"[SMS DISPATCH] Real OTP generated for +91{formatted_phone}: {otp}")
    return False
