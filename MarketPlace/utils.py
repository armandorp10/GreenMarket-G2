import datetime
from MarketPlace.models import Productor, Cliente, Semana, Cooperativa
from django.contrib.auth import logout
from django.shortcuts import redirect, reverse


def es_productor(usuario):
    return Productor.objects.filter(fk_django_user_id=usuario.id).exists()


def es_cliente(usuario):
    return Cliente.objects.filter(fk_django_user_id=usuario.id).exists()


def es_administrador(usuario):
    return usuario.is_staff


def redirect_user_to_home(request):
    if es_productor(request.user):
        return redirect(reverse('productor:index'))
    elif es_cliente(request.user):
        return redirect(reverse('cliente:index'))
    elif es_administrador(request.user):
        return redirect(reverse('administrador:index'))
    else:
        logout(request)
        return redirect(reverse('cliente:index'))


def get_or_create_week():
    today = datetime.date.today()
    existe = Semana.objects.filter(fecha_inicio__lte=today, fecha_fin__gt=today).first()
    if existe:
        return existe
    else:
        prev_monday = today - datetime.timedelta(days=today.weekday())
        next_sunday = prev_monday + datetime.timedelta(weeks=1) - datetime.timedelta(days=1)
        nueva = Semana(
            fk_cooperativa_id=Cooperativa.objects.first().id,
            fecha_inicio=prev_monday,
            fecha_fin=next_sunday
        )
        nueva.save()
        return nueva