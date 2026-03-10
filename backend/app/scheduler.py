"""
Background scheduler for KYFF Store.

Registers a single job that runs every 5 minutes and expires stale
pending / payment_failed orders whose payment window has elapsed.

Registration — call init_scheduler(app) once inside create_app():

    from .scheduler import init_scheduler
    init_scheduler(app)

Requires APScheduler:
    pip install APScheduler==3.10.4
"""

from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler


def _expire_stale_orders(app):
    """
    Finds every order in ('pending', 'payment_failed') whose
    payment_expires_at has passed, restores stock for each item,
    and marks the order as 'expired'.

    Runs inside an explicit app context so it works safely from a
    background thread where Flask's request context is absent.
    """
    with app.app_context():
        from .extensions import db
        from .models import Order, OrderItem, ProductVariant

        # datetime.utcnow() matches the UTC timestamps stored in the DB
        stale = Order.query.filter(
            Order.status.in_(["pending", "payment_failed"]),
            Order.payment_expires_at <= datetime.utcnow()
        ).all()

        if not stale:
            return

        expired_count = 0
        for order in stale:
            # Skip if payment somehow succeeded between query and now
            if order.is_paid():
                continue

            # Restore stock for every item in the order
            for item in OrderItem.query.filter_by(order_id=order.id).all():
                if item.variant_id:
                    variant = ProductVariant.query.get(item.variant_id)
                    if variant:
                        variant.restore_stock(item.quantity)

            order.status = "expired"
            expired_count += 1

        if expired_count:
            db.session.commit()
            print(
                f"[scheduler] {datetime.utcnow().isoformat()} — "
                f"expired {expired_count} stale order(s)"
            )


def init_scheduler(app):
    """
    Creates and starts the background scheduler.
    Call this once at the end of create_app(), after all extensions
    and blueprints have been registered.

    The scheduler is a daemon thread — it stops automatically when the
    Flask development server exits. In production (gunicorn/uWSGI) you
    may want to use APScheduler's SQLAlchemyJobStore or a dedicated
    task queue (Celery + Redis) instead.
    """
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func             = _expire_stale_orders,
        args             = [app],
        trigger          = "interval",
        minutes          = 2,
        id               = "expire_stale_orders",
        replace_existing = True,
    )
    scheduler.start()
    return scheduler

