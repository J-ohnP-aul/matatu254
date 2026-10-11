from django.views.generic import TemplateView

from fleet.models import Matatu


class index(TemplateView):
    template_name = 'fleet/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['matatus'] = Matatu.objects.select_related('qr_code').order_by('registration_number')
        return context