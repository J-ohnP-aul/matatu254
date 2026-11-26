import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from journeys.services import get_active_journey
from .models import Notification
from .signals import deliver_web_push_to_user


@login_required
def notifications(request):
    items = Notification.objects.filter(
        recipient_type=Notification.RecipientType.PASSENGER,
        recipient_id=request.user.id,
    ).order_by('-timestamp')
    return render(request, 'notifications/list.html', {
        'notifications': items,
        'active_journey': get_active_journey(request.user),
        'webpush_public_key': getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", ""),
    })


@login_required
def mark_read(request, pk):
    notification = get_object_or_404(
        Notification,
        pk=pk,
        recipient_type=Notification.RecipientType.PASSENGER,
        recipient_id=request.user.id,
    )
    if notification.status != Notification.Status.READ:
        notification.mark_read()
        messages.success(request, 'Notification marked as read')
    return redirect('notifications:list')


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def push_subscription(request):
    if request.user.role not in ("PASSANGER", "CONDUCTOR"):
        return JsonResponse({"error": "Push notifications are available for passengers and conductors."}, status=403)

    from .models import PushSubscription

    if request.method == "GET":
        return JsonResponse({"publicKey": getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "")})

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request body."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid request body."}, status=400)

    endpoint = data.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        return JsonResponse({"error": "A valid push endpoint is required."}, status=400)

    if request.method == "DELETE":
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return JsonResponse({"ok": True})

    keys = data.get("keys") or {}
    if not isinstance(keys, dict) or not keys.get("p256dh") or not keys.get("auth"):
        return JsonResponse({"error": "The push subscription is incomplete."}, status=400)
    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={"user": request.user, "p256dh": keys["p256dh"], "auth": keys["auth"]},
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def push_test(request):
    """Send an immediate test Web Push notification to the signed-in user's devices."""
    if request.user.role not in ("PASSANGER", "CONDUCTOR"):
        return JsonResponse({"error": "Push notifications are available for passengers and conductors."}, status=403)

    from .models import PushSubscription

    if not getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "") or not getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", ""):
        return JsonResponse({"error": "Phone notifications are not configured on the server yet."}, status=400)

    if not PushSubscription.objects.filter(user=request.user).exists():
        return JsonResponse({"error": "Enable notifications on this device first."}, status=400)

    target_url = (
        reverse("conductor:notifications")
        if request.user.role == "CONDUCTOR"
        else reverse("notifications:list")
    )
    result = deliver_web_push_to_user(
        request.user.pk,
        {
            "title": "Matatu254",
            "body": "Test alert — phone notifications are working on this device.",
            "url": target_url,
            "tag": f"matatu-test-{request.user.pk}",
            "urgent": True,
        },
    )
    if result["sent"] == 0 and result["failed"] > 0:
        return JsonResponse({"error": "Push service rejected delivery for your registered device.", **result}, status=502)
    return JsonResponse({"ok": result["sent"] > 0, **result})
