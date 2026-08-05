# Meta WhatsApp Business API - Setup Guide for Vaidya PHR

This guide walk you through the process of setting up the required keys, IDs, and templates on the Meta Developer Portal and configuring them in your PHR backend.

---

## Step 1: Create a Meta Developer App
1. Go to the [Meta for Developers Portal](https://developers.facebook.com/) and log in with your Facebook/Meta account.
2. Click **My Apps** in the top-right corner.
3. Click the **Create App** button.
4. Select **Other** -> **Next**.
5. Choose **Business** as the app type -> **Next**.
6. Fill in your **App Display Name** (e.g., `Vaidya PHR App`), select your **Business Account** (if you have one, or create/link one), and click **Create App**.

---

## Step 2: Add WhatsApp Product to Your App
1. Inside your new app dashboard, scroll down to **Add products to your app**.
2. Locate **WhatsApp** and click **Set up**.
3. Choose/Create a Meta Business Account if prompted and click **Continue**.

---

## Step 3: Retrieve Temporary API Credentials (For Quick Testing)
Meta provides a sandbox/temporary phone number and token to let you test immediately:
1. In the left-hand sidebar of your app dashboard, expand **WhatsApp** and click **API Setup** (or **Getting Started**).
2. Look at the **Temporary access token** box. Copy this token. *(Note: This token is only valid for 24 hours).*
3. Under **Step 1: Select phone numbers**, locate your **Phone number ID**. Copy this value. *(Note: Do not confuse this with the WhatsApp Business Account ID).*
4. Under **Step 2: To send and receive messages...**, add your own personal mobile number as a verified test recipient. Meta sandbox only allows sending messages to pre-verified numbers. Follow the prompt to verify your phone number via a confirmation code.

---

## Step 4: Generate a Permanent Access Token (For Production)
Temporary tokens expire after 24 hours. For your application to run continuously in production, generate a permanent System User Token:
1. Go to [Meta Business Suite settings](https://business.facebook.com/settings).
2. In the left sidebar, navigate to **Users** -> **System Users**.
3. Click **Add** to create a new system user. 
   - Assign a name (e.g., `vaidya_phr_server`).
   - Set the System User Role to **Admin**.
4. Once created, click on the system user name and click **Generate New Token**.
5. Choose the app you created in Step 1.
6. Under permissions, select **`whatsapp_business_messaging`**.
7. Click **Generate Token**. **Copy and save this token somewhere secure immediately**, as Meta will not display it again.

---

## Step 5: Configure message templates
WhatsApp Business API does not allow businesses to initiate conversations with arbitrary text messages. You must use pre-approved templates.

1. On the WhatsApp **API Setup** page, click the link to **create your own message templates** (or navigate to WhatsApp Manager -> Message Templates).
2. Click **Create Template**:
   - **Category**: Utility
   - **Name**: `otp_verification` (or your preferred name, but make sure to update `WHATSAPP_OTP_TEMPLATE_NAME` in `.env` if different)
   - **Language**: English (or your preferred language code, e.g. `en`)
3. **Template Header**: None
4. **Template Body**: Use a message structure like:
   > "Your Vaidya Health verification code is {{1}}. This code is valid for 5 minutes."
5. **Buttons** (Optional, but default code supports a button parameter):
   - You can add a **Copy Code** button or URL button.
   - *Note: If you do not add buttons to your template in Meta, you must remove the button component block in your backend's [whatsapp_service.py](file:///c:/Users/ranju/OneDrive/Documents/GitHub/Halelabs(Vaidya)/limsAndPhr/Version2/phr/phr_backend1/whatsapp_service.py#L90-L101) to prevent 400 Bad Request errors.*
6. Submit the template for approval. (Approval is usually automatic and takes a few minutes).

---

## Step 6: Add Keys to Your Project
Open the [.env](file:///c:/Users/ranju/OneDrive/Documents/GitHub/Halelabs(Vaidya)/limsAndPhr/Version2/phr/phr_backend1/.env) file in your PHR backend project and configure the keys:

```env
# WhatsApp Integration credentials
WHATSAPP_ACCESS_TOKEN=your_permanent_access_token_here
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here
WHATSAPP_OTP_TEMPLATE_NAME=otp_verification
WHATSAPP_OTP_TEMPLATE_LANGUAGE=en
```

---

## Step 7: Test Your Setup
Once `.env` is updated, run the test script in your backend workspace to check if everything works:

```powershell
python diagnose_whatsapp.py --phone <your-recipient-number>
```
*(Make sure to replace `<your-recipient-number>` with your registered test number, excluding country code, e.g. `9876543210`).*
