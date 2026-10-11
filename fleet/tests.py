from django.test import TestCase
from django.urls import reverse

from fleet.models import Matatu, QRCode


class FleetIndexViewTests(TestCase):
    def test_fleet_index_lists_real_matatus_and_qr_codes(self):
        matatu = Matatu.objects.create(
            registration_number="KAA 123A",
            operator="City Shuttle",
        )
        qr = QRCode.objects.create(
            matatu=matatu,
            code_value="MAT-001",
            status=QRCode.Status.ACTIVE,
        )

        response = self.client.get(reverse("fleet:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matatu.registration_number)
        self.assertContains(response, qr.code_value)
