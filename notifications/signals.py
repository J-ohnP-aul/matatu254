import json
import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Notification, PushSubscription

logger = logging.getLogger(__name__)


def send_web_push(notification_id):
    """Deliver one persisted in-app notification to subscribed devices."""
    public_key = getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "")
    private_key = getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
    if not public_key or not private_key:
        return

    from pywebpush import WebPushException, webpush

    try:
        notification = Notification.objects.get(pk=notification_id)
    except Notification.DoesNotExist:
        return

    payload = json.dumps({
        "title": "Matatu254",
        "body": notification.message,
        "url": "/conductor/notifications/" if notification.recipient_type == Notification.RecipientType.CONDUCTOR else "/notifications/",
        "tag": f"matatu-notification-{notification.pk}",
    })
    for subscription in PushSubscription.objects.filter(user_id=notification.recipient_id):
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": getattr(settings, "WEBPUSH_VAPID_SUBJECT", "mailto:admin@example.com")},
                ttl=3600,
                timeout=5,
            )
        except WebPushException as exc:
            response = getattr(exc, "response", None)
            if response is not None and response.status_code in (404, 410):
                subscription.delete()
            else:
                logger.warning("Web push delivery failed for subscription %s", subscription.pk, exc_info=True)
        except Exception:
            # A push provider outage must not undo the in-app notification or trip update.
            logger.exception("Unexpected web push delivery error for subscription %s", subscription.pk)


@receiver(post_save, sender=Notification)
def queue_notification_push(sender, instance, created, **kwargs):
    if not created:
        return
    from django.db import transaction
    transaction.on_commit(lambda: send_web_push(instance.pk))
