import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from journeys.services import get_active_journey
from .models import Notification


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
