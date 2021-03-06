"""GreenMarket URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from django.contrib import admin
from django.conf.urls.static import static
from django.conf import settings
from GreenMarket.local_settings import IS_DEPLOYED

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^administrador/', include('Administrador.urls', namespace='administrador')),
    url(r'^productor/', include('Productor.urls', namespace='productor')),
    url(r'^repartidor/', include('Repartidor.urls', namespace='repartidor')),
    url(r'^marketplace/', include('MarketPlace.urls', namespace='marketplace')),
    url(r'^', include('Cliente.urls', namespace='cliente')),
]

if IS_DEPLOYED != 'True':
    urlpatterns = urlpatterns + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)