from django.test import TestCase
from django.urls import reverse

from accounts.models import User
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

    def test_matatu_without_qr_links_to_its_qr_management_page(self):
        matatu = Matatu.objects.create(
            registration_number="KVHILL",
            operator="caretaker",
        )

        response = self.client.get(reverse("fleet:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("management:matatu-qr", args=[matatu.pk]),
        )

    def test_create_qr_action_generates_qr_for_existing_matatu(self):
        admin = User.objects.create_user(
            username="fleet-admin",
            password="test-password",
            role=User.ADMIN,
        )
        matatu = Matatu.objects.create(
            registration_number="KVHILL",
            operator="caretaker",
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("management:matatu-qr", args=[matatu.pk]))

        self.assertEqual(response.status_code, 200)
        qr = QRCode.objects.get(matatu=matatu)
        self.assertEqual(qr.code_value, f"MAT-{matatu.pk:04d}")
        self.assertEqual(qr.status, QRCode.Status.ACTIVE)
