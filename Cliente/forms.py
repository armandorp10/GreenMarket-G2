# -*- coding: utf-8 -*-
from django.contrib.auth.forms import forms
from django.forms import ModelForm

from Cliente.models import Cliente


class ClientForm(ModelForm):
    nombre = forms.CharField(max_length=Cliente._meta.get_field('nombre').max_length, label='Nombres')
    apellido = forms.CharField(max_length=Cliente._meta.get_field('apellido').max_length, label='Apellidos')
    departamento = forms.ChoiceField(choices=Cliente._meta.get_field('departamento').choices, label='Departamento')
    ciudad = forms.ChoiceField(choices=Cliente._meta.get_field('ciudad').choices, label='Ciudad')
    numero_identificacion = forms.CharField(max_length=20)
    tipo_identificacion = forms.ChoiceField(choices=Cliente._meta.get_field('tipo_identificacion').choices)
    telefono_contacto = forms.CharField(max_length=15, label='Telefono de Contacto')
    correo = forms.EmailField(max_length=20, label='Correo electrónico')
    direccion = forms.CharField(max_length=150, label='Direcció de Residencia')
    contrasena = forms.CharField(widget=forms.PasswordInput(), label='Contraseña')
    contrasena2 = forms.CharField(widget=forms.PasswordInput(), label='Confirma tu contraseña')
