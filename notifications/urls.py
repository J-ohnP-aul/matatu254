from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notifications, name='list'),
    path('<int:pk>/read/', views.mark_read, name='mark-read'),
    path('push-subscription/', views.push_subscription, name='push-subscription'),
]
