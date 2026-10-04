from io import BytesIO
import base64

import qrcode
from django.views.generic import TemplateView


class index(TemplateView):
    template_name = 'fleet/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        text = "https://fast.com"
        qr = qrcode.make(text)

        buffer = BytesIO()
        qr.save(buffer, format='PNG')
        context['qr'] = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return context