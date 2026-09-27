from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from .models import User

class CustomUserCreationForm(UserCreationForm):
  """
  Form for creating new users with role selection
  """
  phone_number = forms.CharField(max_length=15, required=True)
  role = forms.ChoiceField(choices=User.ROLE_CHOICES, required=True)
  
  class Meta:
      model = User
      fields = ('username', 'first_name', 'last_name', 'phone_number', 
                'email', 'role', 'password1', 'password2')
  
  def clean_phone_number(self):
      phone = self.cleaned_data.get('phone_number')
      if User.objects.filter(phone_number=phone).exists():
          raise forms.ValidationError('This phone number is already registered.')
      return phone

class CustomAuthenticationForm(AuthenticationForm):
  """
  Login form
  """
  username = forms.CharField(widget=forms.TextInput(attrs={
      'class': 'form-control',
      'placeholder': 'Username'
  }))
  password = forms.CharField(widget=forms.PasswordInput(attrs={
      'class': 'form-control',
      'placeholder': 'Password'
  }))
  
  def clean(self):
      username = self.cleaned_data.get('username')
      password = self.cleaned_data.get('password')
      
      if username and password:
          self.user_cache = authenticate(username=username, password=password)
          if self.user_cache is None:
              raise forms.ValidationError('Invalid username or password.')
          elif not self.user_cache.is_active:
              raise forms.ValidationError('This account is inactive.')
      return self.cleaned_data