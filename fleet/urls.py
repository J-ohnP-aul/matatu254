from django.urls import path

from .views import index

app_name = "fleet"

urlpatterns = [
    path('', index.as_view(), name='index'),
]
