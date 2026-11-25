from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required


from .forms import CustomUserCreationForm, ProfileImageForm
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


@login_required
def profile(request):
  old_image = request.user.profile_image
  if request.method == 'POST':
    form = ProfileImageForm(request.POST, request.FILES, instance=request.user)
    if form.is_valid():
      user = form.save()
      if old_image and old_image.name != user.profile_image.name:
        old_image.delete(save=False)
      messages.success(request, 'Your profile photo was updated.')
      return redirect('accounts:profile')
  else:
    form = ProfileImageForm(instance=request.user)
  return render(request, "accounts/profile.html", {'form': form})
