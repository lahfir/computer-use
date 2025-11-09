# Twilio Phone Verification

Complete guide for SMS verification automation with the Browser agent using CrewAI and Browser-Use.

---

## Table of Contents

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Setup Instructions](#setup-instructions)
- [Available Tools](#available-tools)
- [Integration with Browser Agent](#integration-with-browser-agent)
- [Troubleshooting](#troubleshooting)
- [Technical Details](#technical-details)

---

## Quick Start (5 Minutes)

### 1. Get Twilio Credentials

1. Sign up: [twilio.com/try-twilio](https://www.twilio.com/try-twilio)
2. Get from [Console](https://www.twilio.com/console):
   - Account SID (starts with `AC`)
   - Auth Token
3. Buy phone number: [Phone Numbers → Buy](https://www.twilio.com/console/phone-numbers/search)
   - Choose a number with SMS capability
   - Cost: ~$1/month

### 2. Configure Environment

Add to your `.env` file:

```bash
# Twilio Phone Verification (Optional)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890
```

### 3. Install & Setup Webhook

```bash
# Dependencies are already included in main installation
# No additional steps needed

# Start the application (webhook runs automatically on port 5001)
uv run python -m computer_use.main
```

**On startup, you'll see**:
```
🚀 Initializing Systems
✅ Twilio configured: +1234567890
📡 Webhook server started on http://localhost:5001
```

### 4. Configure Twilio Webhook (One-Time Setup)

#### Option A: Using ngrok (Recommended for Testing)

```bash
# Terminal 1: Run the application
uv run python -m computer_use.main

# Terminal 2: Expose webhook publicly
ngrok http 5001
```

**Configure Twilio**:
1. Go to [Phone Numbers](https://www.twilio.com/console/phone-numbers/incoming)
2. Click your number → **Messaging** section
3. **A MESSAGE COMES IN:**
   - Webhook: `https://YOUR-NGROK-URL.ngrok.io/sms`
   - Method: POST
4. Click **Save**

#### Option B: Production Deployment

Deploy your application to a server with a public domain:

1. Ensure application runs on port 5001
2. Configure webhook: `https://yourdomain.com/sms`
3. Ensure HTTPS is enabled (Twilio requires HTTPS)

### 5. Test It

```bash
# Run the application
uv run python -m computer_use.main

# Try a task with phone verification
💬 Enter your task:
➤ Sign up for an account on example.com
```

**The Browser agent will automatically**:
1. Detect phone verification field
2. Call `get_verification_phone_number()` to get Twilio number
3. Enter the number in the form
4. Wait for SMS via `get_verification_code(timeout=60)`
5. Enter the received code
6. Complete signup

---

## How It Works

### Architecture

```
Website sends SMS
    ↓
Twilio receives SMS
    ↓
Twilio forwards to Webhook (POST /sms)
    ↓
WebhookServer stores message in TwilioService
    ↓
Browser agent polls for message
    ↓
TwilioService uses LLM to extract code from SMS
    ↓
Browser agent receives code and continues
```

### Components

#### 1. TwilioService (`src/computer_use/services/twilio_service.py`)

**Responsibilities**:
- Store incoming SMS messages
- Extract verification codes using LLM
- Provide Twilio phone number to agents
- Thread-safe message storage

**Key Methods**:
```python
class TwilioService:
    def get_phone_number(self) -> Optional[str]:
        """Get Twilio phone number for verification."""
    
    def store_message(self, from_number: str, to_number: str, body: str):
        """Store incoming SMS message."""
    
    async def get_verification_code(self, timeout: int = 60) -> Optional[str]:
        """Poll for SMS and extract verification code using LLM."""
    
    def is_configured(self) -> bool:
        """Check if Twilio credentials are set."""
```

#### 2. WebhookServer (`src/computer_use/services/webhook_server.py`)

**Responsibilities**:
- Run Flask server in background thread
- Receive Twilio POST requests
- Pass messages to TwilioService

**Implementation**:
```python
class WebhookServer:
    """Flask server for receiving Twilio webhooks."""
    
    def __init__(self, twilio_service: TwilioService):
        self.twilio_service = twilio_service
        self.app = Flask(__name__)
        self._setup_routes()
    
    def start(self):
        """Start webhook server in daemon thread."""
        thread = Thread(
            target=self._run_server,
            daemon=True  # Closes with main app
        )
        thread.start()
```

#### 3. Browser Agent Integration

**Tools Available**:
- `get_verification_phone_number()`: Get Twilio number
- `get_verification_code(timeout=60)`: Wait for SMS code
- `request_human_help()`: Escalate if needed

**Automatic Usage**:
The Browser agent (via Browser-Use) automatically detects phone verification and uses these tools.

---

## Setup Instructions

### Step 1: Twilio Account Setup

1. **Create Account**:
   - Visit [twilio.com/try-twilio](https://www.twilio.com/try-twilio)
   - Sign up (free trial includes $15.50 credit)

2. **Get Credentials**:
   - Go to [Twilio Console](https://www.twilio.com/console)
   - Find **Account SID** and **Auth Token**
   - Copy both values

3. **Buy Phone Number**:
   - Navigate to [Phone Numbers → Buy a Number](https://www.twilio.com/console/phone-numbers/search)
   - Filter by: **SMS** capability
   - Select country (e.g., United States)
   - Choose a number and purchase (~$1/month)

### Step 2: Environment Configuration

Create or update `.env` file:

```bash
# ==============================================
# Twilio Phone Verification (Optional)
# ==============================================

# Your Twilio Account SID (starts with AC)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Your Twilio Auth Token
TWILIO_AUTH_TOKEN=your_auth_token_here

# Your Twilio Phone Number (E.164 format: +1234567890)
TWILIO_PHONE_NUMBER=+1234567890

# Optional: Custom webhook port (default: 5001)
WEBHOOK_PORT=5001
```

### Step 3: Webhook Configuration

#### Development (ngrok)

```bash
# Terminal 1: Start application
uv run python -m computer_use.main

# Terminal 2: Start ngrok
ngrok http 5001

# You'll see output like:
# Forwarding https://abc123.ngrok.io -> http://localhost:5001
```

**Configure in Twilio**:
1. Copy the `https://` URL from ngrok
2. Go to [Twilio Console → Phone Numbers](https://www.twilio.com/console/phone-numbers/incoming)
3. Click your number
4. Scroll to **Messaging** section
5. Under "A MESSAGE COMES IN":
   - Webhook URL: `https://abc123.ngrok.io/sms`
   - HTTP Method: `POST`
6. Click **Save**

#### Production (Permanent URL)

If you have a deployed server with a domain:

```bash
# Configure webhook
https://yourdomain.com/sms
```

**Requirements**:
- HTTPS enabled (Twilio requires secure webhooks)
- Port 5001 accessible (or configure custom port)
- Application running continuously

### Step 4: Verify Setup

```bash
# Test webhook health
curl http://localhost:5001/health

# Expected response:
{"status": "ok"}

# Check Twilio status in app
# When you start the app, you should see:
✅ Twilio configured: +1234567890
📡 Webhook server started on http://localhost:5001
```

---

## Available Tools

### For Browser Agent (Automatic)

The Browser agent has access to these tools via Browser-Use:

#### 1. get_verification_phone_number

```python
# Browser-Use action
get_verification_phone_number()

# Returns: "+1234567890" (your Twilio number)
```

**Usage**: Browser agent automatically calls this when it detects a phone verification field.

#### 2. get_verification_code

```python
# Browser-Use action
get_verification_code(timeout=60, poll_interval=1.0)

# Parameters:
#   timeout: Max seconds to wait for SMS (default: 60)
#   poll_interval: How often to check for messages (default: 1.0)

# Returns: "123456" (extracted code)
```

**Usage**: Browser agent calls this after submitting phone number and waits for SMS.

**How it works**:
1. Polls TwilioService every 1 second
2. When SMS arrives, uses LLM to extract code
3. Returns code or None if timeout

#### 3. request_human_help

```python
# Browser-Use action
request_human_help(
    reason="Cannot bypass CAPTCHA",
    instructions="Please solve the CAPTCHA and press Enter to continue"
)
```

**Usage**: Browser agent escalates to human when automated verification isn't possible.

---

## Integration with Browser Agent

### Automatic Phone Verification Flow

The Browser agent automatically handles phone verification:

```
1. Browser navigates to signup page
2. Detects phone input field
3. Calls get_verification_phone_number()
   → Receives: "+1234567890"
4. Enters phone number and submits
5. Website sends SMS to Twilio number
6. Twilio forwards to webhook (POST /sms)
7. Webhook stores message in TwilioService
8. Browser calls get_verification_code(timeout=60)
9. TwilioService polls for new messages
10. LLM extracts code from SMS
11. Browser receives code: "123456"
12. Browser enters code and completes signup
```

### Example Task

```bash
💬 Enter your task:
➤ Sign up for Discord with email user@example.com

# Browser agent will:
# 1. Navigate to discord.com/register
# 2. Fill in email field
# 3. Detect phone verification
# 4. Automatically use Twilio number
# 5. Wait for SMS code
# 6. Enter code and complete signup
```

### SMS Code Extraction

The TwilioService uses an LLM to extract codes from various SMS formats:

**Supported Formats**:
```
"Your verification code is 123456"
"123456 is your verification code"
"Use code 123456 to verify your account"
"Your OTP: 123456"
"Discord verification code: 123456"
"Enter this code: 123456"
```

**LLM Prompt**:
```python
prompt = f"""
Extract the numeric verification code from this SMS message:

"{sms_body}"

Return ONLY the numeric code (usually 4-6 digits).
If no code is found, return "NONE".
"""
```

**Example**:
```python
SMS: "Your Discord verification code is 847293"
LLM extracts: "847293"
```

---

## Troubleshooting

### No SMS Received

**Check webhook is running**:
```bash
curl http://localhost:5001/health
# Expected: {"status": "ok"}
```

**Check ngrok is running** (if using ngrok):
```bash
# Should show active tunnel
ngrok http 5001
```

**Check Twilio logs**:
1. Go to [Twilio Console → Monitor → Logs → Messaging](https://www.twilio.com/console/sms/logs)
2. Look for recent messages
3. Check for delivery errors

**Common Issues**:
- ❌ Webhook URL not configured in Twilio
- ❌ ngrok tunnel expired (restart ngrok)
- ❌ Firewall blocking webhook port
- ❌ Wrong phone number format (use E.164: +1234567890)

### Code Extraction Fails

**Symptoms**:
```
⚠️  Code confidence too low: 0.45
❌ LLM extraction error
```

**Solutions**:
1. Check SMS format is standard
2. Verify LLM API key is configured
3. Check LLM provider is responding

**Debug**:
```python
# Check stored messages
# In TwilioService, messages are stored with timestamps
# Recent messages expire after 5 minutes
```

### Webhook Not Receiving

**Test manually**:
```bash
curl -X POST http://localhost:5001/sms \
  -d "From=+1234567890" \
  -d "To=+1987654321" \
  -d "Body=Your verification code is 123456"

# Expected: Empty response (200 OK)
```

**Check application logs**:
```
📡 Webhook server started on http://localhost:5001
📨 Received SMS from +1234567890: "Your verification code is..."
```

### Timeout Errors

**Symptom**:
```
⏱️  Timeout waiting for verification code (60 seconds)
```

**Causes**:
- SMS delivery delayed (can take 10-30 seconds)
- Webhook not configured correctly
- Message not reaching TwilioService

**Solutions**:
1. Increase timeout: `get_verification_code(timeout=120)`
2. Check webhook configuration
3. Verify SMS was sent by website

---

## Technical Details

### Thread Safety

**Message Storage**:
```python
class TwilioService:
    def __init__(self):
        self.messages = []
        self.lock = threading.Lock()  # Thread-safe access
    
    def store_message(self, ...):
        with self.lock:  # Synchronized access
            self.messages.append({
                'from': from_number,
                'to': to_number,
                'body': body,
                'timestamp': time.time()
            })
```

**Webhook Server**:
- Runs in daemon thread (closes with main app)
- Flask handles concurrent requests
- TwilioService synchronizes message access

### Performance

| Operation | Typical Time |
|-----------|-------------|
| Get phone number | < 1ms |
| Store SMS | < 5ms |
| Poll for message | 1s intervals |
| LLM extraction | 1-3 seconds |
| Total verification | 10-30 seconds |

**Polling Strategy**:
```python
async def get_verification_code(self, timeout=60, poll_interval=1.0):
    """Poll for SMS with configurable interval."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Check for new messages
        messages = self._get_recent_messages()
        
        if messages:
            # Extract code using LLM
            code = await self._extract_code(messages[0]['body'])
            if code:
                return code
        
        # Wait before next poll
        await asyncio.sleep(poll_interval)
    
    return None  # Timeout
```

### Security

**Message Expiry**:
```python
def _get_recent_messages(self, max_age=300):
    """Get messages from last 5 minutes only."""
    cutoff = time.time() - max_age
    with self.lock:
        return [m for m in self.messages if m['timestamp'] > cutoff]
```

**Memory Storage**:
- Messages stored in-memory only
- Not persisted to disk
- Automatically cleared on restart
- Expire after 5 minutes

**HTTPS Requirement**:
- Twilio requires HTTPS for webhooks in production
- Use ngrok (automatic HTTPS) for development
- Deploy with SSL certificate for production

### Rate Limiting

**Twilio Limits**:
- Free trial: Limited messages per day
- Paid account: Higher limits
- Check [Twilio pricing](https://www.twilio.com/sms/pricing)

**Application**:
- No built-in rate limiting
- Relies on Browser agent's max_steps limit
- Max one verification per task execution

---

## Advanced Configuration

### Custom Webhook Port

```bash
# .env
WEBHOOK_PORT=8080

# Application will use custom port
📡 Webhook server started on http://localhost:8080
```

### ngrok Auth Token (Persistent URLs)

```bash
# Get auth token from: https://dashboard.ngrok.com/get-started/your-authtoken
ngrok config add-authtoken YOUR_TOKEN

# Start with custom subdomain (paid feature)
ngrok http 5001 --subdomain=myapp-webhook
```

### Multiple Phone Numbers

Currently supports one Twilio number per configuration. For multiple numbers:

1. Use separate `.env` files
2. Run multiple instances
3. Or extend `TwilioService` to support number selection

---

## Production Deployment

### Checklist

- [ ] Deploy application to server with public domain
- [ ] Configure HTTPS (required by Twilio)
- [ ] Set webhook URL: `https://yourdomain.com/sms`
- [ ] Verify webhook receives POST requests
- [ ] Monitor Twilio logs for delivery
- [ ] Set up error alerting
- [ ] Implement webhook signature validation (optional security)

### Webhook Signature Validation (Optional)

For additional security, validate Twilio webhook signatures:

```python
from twilio.request_validator import RequestValidator

validator = RequestValidator(auth_token)

@app.route('/sms', methods=['POST'])
def sms_webhook():
    signature = request.headers.get('X-Twilio-Signature', '')
    url = request.url
    params = request.form.to_dict()
    
    if not validator.validate(url, params, signature):
        return 'Invalid signature', 403
    
    # Process webhook
    # ...
```

---

## Files Reference

**Service Files**:
- `src/computer_use/services/twilio_service.py` - Core SMS service
- `src/computer_use/services/webhook_server.py` - Flask webhook server

**Tool Files**:
- `src/computer_use/tools/twilio_controller.py` - Browser-Use actions

**Integration**:
- `src/computer_use/tools/browser_tool.py` - Browser agent integration
- `src/computer_use/main.py` - Service initialization

**Configuration**:
- `.env` - Twilio credentials
- `pyproject.toml` - Dependencies (twilio, flask, pyngrok)

---

## Resources

- [Twilio SMS Documentation](https://www.twilio.com/docs/sms)
- [Twilio Webhooks Guide](https://www.twilio.com/docs/usage/webhooks)
- [Browser-Use Documentation](https://browser-use.com/)
- [ngrok Documentation](https://ngrok.com/docs)

---

**Twilio integration enables fully automated phone verification for signups and 2FA!** 📱✅
