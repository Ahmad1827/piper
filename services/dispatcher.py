import hmac
import hashlib
import json
import httpx
from typing import Dict, Any

async def dispatch_tenant_webhook(webhook_url: str, secret: str, event_type: str, data: Dict[str, Any]) -> bool:
    payload = {
        "event": event_type,
        "data": data
    }
    encoded_body = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    signature = hmac.new(secret.encode('utf-8'), encoded_body, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Piper-Signature": signature
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(webhook_url, content=encoded_body, headers=headers)
            return 200 <= response.status_code < 300
        except httpx.RequestError:
            return False
