from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
from models import CheckoutSession

class BasePaymentProvider(ABC):
    @abstractmethod
    async def create_charge_intent(self, session: CheckoutSession) -> Tuple[str, str]:
        pass

    @abstractmethod
    def parse_and_verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        pass
