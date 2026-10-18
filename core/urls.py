from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
  path('', views.home, name="home"),
  path('offline/', views.offline, name="offline"),
  path('dashboard/', views.dashboard, name="dashboard"),
]
