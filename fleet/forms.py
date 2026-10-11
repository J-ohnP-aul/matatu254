from django import forms
from .models import Matatu, QRCode

class MatatuForm(forms.ModelForm):
    class Meta:
      model = Matatu
      fields = ['registration_number', "operator", 'owner']
      
      widgets = {
        'registration_number': forms.TextInput(attrs={'class': 'form-control'}),
        'operator': forms.TextInput(attrs={'class': 'form-control'}),
        'owner': forms.Select(attrs={'class': 'form-control'}),
      }
      
class QRCodeForm(forms.ModelForm):
    class Meta:
        model = QRCode
        fields = ['matatu', 'code_value', 'status']
        
        widgets = {
            'matatu': forms.Select(attrs={'class': 'form-control'}),
            'code_value': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }