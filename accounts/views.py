from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout


from .forms import CustomUserCreationForm
from .models import User

# Create your views here.


def register(request):
  if request.method == 'POST':
    form = CustomUserCreationForm(request.POST)
    if form.is_valid():
      user = form.save()
      login(request, user) #login user after registration
      messages.success(request, f'User {user.username} created successfully!')
      return redirect("core:dashboard")
  else:
    form = CustomUserCreationForm()
  return render(request, "accounts/register.html", {'form':form})

def log_out(request):
  logout(request)
  return redirect("core:home")