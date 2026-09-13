import secrets
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Security, Request, Header
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db, engine, Base
from models import Tenant, CheckoutSession, Transaction
from schemas import TenantCreateRequest, TenantResponse, SessionCreateRequest, SessionResponse
from providers.stripe_provider import StripeProvider
from services.dispatcher import dispatch_tenant_webhook

app = FastAPI(title="Piper")
templates = Jinja2Templates(directory="templates")
security = HTTPBearer()
stripe_provider = StripeProvider()

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def authenticate_tenant(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    query = select(Tenant).where(Tenant.api_key == credentials.credentials)
    result = await db.execute(query)
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return tenant

@app.post("/api/v1/tenants", response_model=TenantResponse)
async def create_tenant(payload: TenantCreateRequest, db: AsyncSession = Depends(get_db)):
    api_key = f"piper_live_{secrets.token_urlsafe(24)}"
    webhook_secret = f"whsec_{secrets.token_urlsafe(24)}"

    tenant = Tenant(
        name=payload.name,
        api_key=api_key,
        webhook_url=str(payload.webhook_url),
        webhook_secret=webhook_secret
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        api_key=tenant.api_key,
        webhook_secret=tenant.webhook_secret,
        webhook_url=tenant.webhook_url
    )

@app.post("/api/v1/sessions", response_model=SessionResponse)
async def create_checkout_session(
    payload: SessionCreateRequest,
    tenant: Tenant = Depends(authenticate_tenant),
    db: AsyncSession = Depends(get_db)
):
    session_id = f"pipe_{secrets.token_urlsafe(16)}"
    expires_at = datetime.utcnow() + timedelta(hours=2)

    session = CheckoutSession(
        id=session_id,
        tenant_id=tenant.id,
        amount_cents=payload.amount_cents,
        currency=payload.currency.upper(),
        item_name=payload.item_name,
        customer_email=payload.customer_email,
        metadata_=payload.metadata or {},
        status="pending",
        success_url=str(payload.success_url),
        cancel_url=str(payload.cancel_url),
        provider="stripe",
        expires_at=expires_at
    )

    intent_id, client_secret = await stripe_provider.create_charge_intent(session)
    session.provider_intent_id = intent_id
    session.client_secret = client_secret

    db.add(session)
    await db.commit()

    return SessionResponse(
        session_id=session_id,
        checkout_url=f"{settings.SERVICE_BASE_URL}/gate/{session_id}",
        status=session.status
    )

@app.get("/gate/{session_id}", response_class=HTMLResponse)
async def render_gate(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    query = select(CheckoutSession).where(CheckoutSession.id == session_id)
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if not session or session.status != "pending":
        raise HTTPException(status_code=404, detail="Session not found or expired")

    formatted_amount = f"{session.amount_cents / 100:.2f} {session.currency}"

    return templates.TemplateResponse(
        request=request,
        name="gate.html",
        context={
            "session": session,
            "formatted_amount": formatted_amount,
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY
        }
    )

@app.post("/api/v1/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None), db: AsyncSession = Depends(get_db)):
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    payload = await request.body()
    try:
        event = stripe_provider.parse_and_verify_webhook(payload, stripe_signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        intent_id = intent["id"]

        query = select(CheckoutSession).where(CheckoutSession.provider_intent_id == intent_id)
        result = await db.execute(query)
        session = result.scalar_one_or_none()

        if session and session.status == "pending":
            session.status = "completed"

            tx = Transaction(
                session_id=session.id,
                tenant_id=session.tenant_id,
                provider="stripe",
                provider_tx_id=intent_id,
                amount_cents=session.amount_cents,
                currency=session.currency,
                status="succeeded",
                raw_payload=intent
            )
            db.add(tx)
            await db.commit()

            tenant_query = select(Tenant).where(Tenant.id == session.tenant_id)
            t_res = await db.execute(tenant_query)
            tenant = t_res.scalar_one()

            event_data = {
                "session_id": session.id,
                "amount_cents": session.amount_cents,
                "currency": session.currency,
                "customer_email": session.customer_email,
                "metadata": session.metadata_
            }
            await dispatch_tenant_webhook(
                webhook_url=tenant.webhook_url,
                secret=tenant.webhook_secret,
                event_type="payment.succeeded",
                data=event_data
            )

    return {"status": "success"}
