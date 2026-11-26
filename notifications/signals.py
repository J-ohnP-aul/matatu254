from concurrent.futures import ThreadPoolExecutor
import json
import logging

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from .models import Notification, PushSubscription

logger = logging.getLogger(__name__)
_PUSH_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webpush")


def _vapid_config():
    """Return configured VAPID public key, private key, and subject."""
    return (
        getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", ""),
        getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", ""),
        getattr(settings, "WEBPUSH_VAPID_SUBJECT", "mailto:admin@example.com"),
    )


def deliver_web_push_to_user(user_id, payload_dict):
    """Send one Web Push payload to every subscribed device for a user."""
    public_key, private_key, subject = _vapid_config()
    if not public_key or not private_key:
        return {"sent": 0, "failed": 0, "configured": False}

    from pywebpush import WebPushException, webpush

    payload = json.dumps(payload_dict)
    sent = 0
    failed = 0
    for subscription in PushSubscription.objects.filter(user_id=user_id):
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
                ttl=3600,
                timeout=5,
            )
            sent += 1
        except WebPushException as exc:
            failed += 1
            response = getattr(exc, "response", None)
            if response is not None and response.status_code in (404, 410):
                subscription.delete()
            else:
                logger.warning("Web push delivery failed for subscription %s", subscription.pk, exc_info=True)
        except Exception:
            # A push provider outage must not undo the in-app notification or trip update.
            failed += 1
            logger.exception("Unexpected web push delivery error for subscription %s", subscription.pk)
    return {"sent": sent, "failed": failed, "configured": True}


def _notification_title_and_url(notification):
    """Build mobile notification title and tap target URL for a Notification."""
    if notification.recipient_type == Notification.RecipientType.CONDUCTOR:
        url = reverse("conductor:notifications")
        lowered = notification.message.lower()
        if "trip cancelled" in lowered:
            title = "Trip cancelled"
        elif "trip ended" in lowered:
            title = "Trip ended"
        elif "arrived" in lowered:
            title = "Passenger arrived"
        else:
            title = "Matatu254 Crew"
        return title, url

    url = (
        reverse("journeys:journey-detail", args=[notification.journey_id])
        if notification.journey_id
        else reverse("notifications:list")
    )
    title = "You have arrived" if "arrived" in notification.message.lower() else "Matatu254"
    return title, url


def send_web_push(notification_id):
    """Deliver one persisted in-app notification to subscribed devices."""
    public_key, private_key, _subject = _vapid_config()
    if not public_key or not private_key:
        return

    try:
        notification = Notification.objects.get(pk=notification_id)
    except Notification.DoesNotExist:
        return

    if not notification.send_push:
        return

    title, target_url = _notification_title_and_url(notification)
    deliver_web_push_to_user(
        notification.recipient_id,
        {
            "title": title,
            "body": notification.message,
            "url": target_url,
            "tag": f"matatu-notification-{notification.pk}",
            "urgent": True,
        },
    )


def _send_web_push_worker(notification_id):
    close_old_connections()
    try:
        send_web_push(notification_id)
    finally:
        close_old_connections()


@receiver(post_save, sender=Notification)
def queue_notification_push(sender, instance, created, **kwargs):
    if not created or not instance.send_push:
        return
    notification_id = instance.pk

    def _dispatch():
        if getattr(settings, "WEBPUSH_ASYNC", True):
            _PUSH_EXECUTOR.submit(_send_web_push_worker, notification_id)
        else:
            send_web_push(notification_id)

    transaction.on_commit(_dispatch)
