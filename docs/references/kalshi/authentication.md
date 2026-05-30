> Source: https://docs.kalshi.com/getting_started/api_keys.md, https://docs.kalshi.com/getting_started/quick_start_authenticated_requests.md (scraped 2026-05-30)

# Authentication

Kalshi authenticates API requests with an **RSA key pair**. You hold the private key; Kalshi stores the public key and a Key ID. Each request is signed with the private key using **RSA-PSS over SHA-256**.

## Generating an API Key

1. Log into your Kalshi account and go to Profile Settings: `https://kalshi.com/account/profile`.
2. In the **API Keys** section, click **Create New API Key**.
3. Kalshi generates and returns:
   - **Private Key** — a secret credential in `RSA_PRIVATE_KEY` (PEM) format.
   - **Key ID** — a UUID that identifies the key.
4. **Save the private key immediately.** "The private key will not be stored by our service, and you will not be able to retrieve it again once this page is closed." If lost, it cannot be recovered — you must generate a new key.

API keys are environment-specific (production vs demo).

## Required Headers

Every authenticated request must include three headers:

| Header | Value |
|---|---|
| `KALSHI-ACCESS-KEY` | Your API Key ID (UUID). |
| `KALSHI-ACCESS-TIMESTAMP` | Current time as a Unix timestamp in **milliseconds**. |
| `KALSHI-ACCESS-SIGNATURE` | Base64-encoded RSA-PSS-SHA256 signature of the signing string. |

## Signing String

Concatenate, with no separators:

```
timestamp + HTTP_METHOD + path
```

- `timestamp` — the same millisecond timestamp sent in `KALSHI-ACCESS-TIMESTAMP`.
- `HTTP_METHOD` — uppercase verb, e.g. `GET`, `POST`, `DELETE`.
- `path` — the request path **including the `/trade-api/v2` prefix** and **excluding any query parameters**.

Example message: `1703123456789GET/trade-api/v2/portfolio/balance`

Sign the UTF-8 bytes of this message with the private key using **RSA-PSS** padding (MGF1 with SHA-256, salt length = digest length) and **SHA-256** hashing, then **Base64-encode** the result.

### Important details

- Strip query parameters from the path **before** signing.
- Timestamps are in **milliseconds**, not seconds.
- Include the full path from root (the `/trade-api/v2/...` prefix), not just the resource path.
- For WebSocket connections, the signed path is `/trade-api/ws/v2` and the method is `GET` (see `websocket.md`).

## Signing Function (Python)

```python
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

def sign_request(private_key, timestamp, method, path):
    # Strip query parameters from path before signing
    path_without_query = path.split('?')[0]

    # Create the message to sign
    message = f"{timestamp}{method}{path_without_query}".encode('utf-8')

    # Sign with RSA-PSS
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH
        ),
        hashes.SHA256()
    )

    # Return base64 encoded
    return base64.b64encode(signature).decode('utf-8')
```

## Basic Authenticated Request (Python)

```python
import requests
import datetime

# Set up the request
timestamp = str(int(datetime.datetime.now().timestamp() * 1000))
method = "GET"
path = "/trade-api/v2/portfolio/balance"

# Create signature (using function above)
signature = sign_request(private_key, timestamp, method, path)

# Make the request
headers = {
    'KALSHI-ACCESS-KEY': 'your-api-key-id',
    'KALSHI-ACCESS-SIGNATURE': signature,
    'KALSHI-ACCESS-TIMESTAMP': timestamp
}

response = requests.get('https://external-api.demo.kalshi.co' + path, headers=headers)
balance = response.json()

print(f"Your balance: ${balance['balance'] / 100:.2f}")
```

## Complete Working Example (Python)

```python
import requests
import datetime
import base64
from urllib.parse import urlparse
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration
API_KEY_ID = 'your-api-key-id-here'
PRIVATE_KEY_PATH = 'path/to/your/kalshi-key.key'
BASE_URL = 'https://external-api.demo.kalshi.co/trade-api/v2'  # or 'https://external-api.kalshi.com/trade-api/v2' for production

def load_private_key(key_path):
    with open(key_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

def create_signature(private_key, timestamp, method, path):
    """Create the request signature."""
    # Strip query parameters before signing
    path_without_query = path.split('?')[0]
    message = f"{timestamp}{method}{path_without_query}".encode('utf-8')
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def get(private_key, api_key_id, path, base_url=BASE_URL):
    """Make an authenticated GET request to the Kalshi API."""
    timestamp = str(int(datetime.datetime.now().timestamp() * 1000))
    # Signing requires the full URL path from root (e.g. /trade-api/v2/portfolio/balance)
    sign_path = urlparse(base_url + path).path
    signature = create_signature(private_key, timestamp, "GET", sign_path)

    headers = {
        'KALSHI-ACCESS-KEY': api_key_id,
        'KALSHI-ACCESS-SIGNATURE': signature,
        'KALSHI-ACCESS-TIMESTAMP': timestamp
    }

    return requests.get(base_url + path, headers=headers)

# Load private key
private_key = load_private_key(PRIVATE_KEY_PATH)

# Get balance
response = get(private_key, API_KEY_ID, "/portfolio/balance")
print(f"Your balance: ${response.json()['balance'] / 100:.2f}")
```

> Note: Many market-data endpoints (e.g. GetMarkets, GetMarket, orderbook) are publicly accessible without authentication. Portfolio, order, and fill endpoints require the signed headers above.
