from types import SimpleNamespace

from sqlalchemy import select

from app.database import SessionLocal
from app.models import User
from app.services.billing import process_event
from app.services.seeds import seed_database


def test_subscription_webhook_is_idempotent():
    with SessionLocal() as db:
        seed_database(db)
        user = db.scalar(select(User).where(User.email == "demo@dealsig.ai"))
        user.stripe_customer_id = "cus_test"
        user.subscription_status = "inactive"
        db.commit()
        event = SimpleNamespace(
            id="evt_test_1",
            type="customer.subscription.updated",
            data=SimpleNamespace(
                object={"id": "sub_test", "customer": "cus_test", "status": "active"}
            ),
        )
        assert process_event(db, event) is True
        assert process_event(db, event) is False
        db.refresh(user)
        assert user.subscription_status == "active"

