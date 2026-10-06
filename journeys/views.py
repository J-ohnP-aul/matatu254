from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from fleet.models import QRCode
from trips.models import ActiveTrip
from r_outes.models import Stage


def scan_qr(request):
    """Render the camera scanner page"""
    return render(request, "journeys/scan.html")


def scan_result(request):
    """Process scanned QR code_value"""
    if request.method != "POST":
        return redirect("journeys:scan-qr")

    code_value = request.POST.get("code_value", "").strip()
    if not code_value:
        messages.error(request, "No QR code data received")
        return redirect("journeys:scan-qr")

    # Lookup QRCode -> Matatu -> ActiveTrip
    qr = get_object_or_404(QRCode, code_value=code_value, status=QRCode.Status.ACTIVE)
    matatu = qr.matatu
    trip = ActiveTrip.objects.filter(
        matatu=matatu,
        status=ActiveTrip.Status.ACTIVE
    ).first()

    if not trip:
        messages.error(request, "This matatu has no active trip right now")
        return redirect("journeys:scan-qr")

    return redirect("journeys:trip-stages", trip_id=trip.id)


def trip_stages(request, trip_id):
    trip = get_object_or_404(ActiveTrip, pk=trip_id, status=ActiveTrip.Status.ACTIVE)
    stages = trip.route.stages.order_by("sequence_order")
    return render(request, "journeys/stages.html", {"trip": trip, "stages": stages})