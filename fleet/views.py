from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from fleet.models import Matatu


def is_admin(user):
    return user.is_authenticated and user.role == 'ADMIN'


@method_decorator(login_required, name='dispatch')
@method_decorator(user_passes_test(is_admin), name='dispatch')
class index(TemplateView):
    """Fleet listing for management. Admin-only: the QR codes shown here are
    the boarding credential, so the page must not be publicly enumerable."""
    template_name = 'fleet/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['matatus'] = Matatu.objects.select_related('qr_code').order_by('registration_number')
        return context
