import stripe
from typing import Tuple, Dict, Any
from config import settings
from models import CheckoutSession
from providers.base import BasePaymentProvider

stripe.api_key = settings.STRIPE_SECRET_KEY

class StripeProvider(BasePaymentProvider):
    async def create_charge_intent(self, session: CheckoutSession) -> Tuple[str, str]:
        intent_params = {
            "amount": session.amount_cents,
            "currency": session.currency.lower(),
            "metadata": {
                "session_id": session.id,
                "tenant_id": str(session.tenant_id),
            },
            "automatic_payment_methods": {"enabled": True},
        }
        if session.customer_email:
            intent_params["receipt_email"] = session.customer_email

        intent = stripe.PaymentIntent.create(**intent_params)
        return intent.id, intent.client_secret

    def parse_and_verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=settings.STRIPE_WEBHOOK_SECRET
        )
        return event
