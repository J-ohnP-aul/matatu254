from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notification


@login_required
def notifications(request):
    items = Notification.objects.filter(
        recipient_type=Notification.RecipientType.PASSENGER,
        recipient_id=request.user.id,
    ).order_by('-timestamp')
    return render(request, 'notifications/list.html', {'notifications': items})


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
