# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
from django.db.models import Sum, Min, Max
from django.shortcuts import render
from django.views import View
from MarketPlace.models import Oferta, Oferta_Producto, Producto
from django.http import JsonResponse


class Index(View):
    def get(self, request):
        return render(request, 'Administrador/index.html', {})

class CatalogoView(View):
    def get(self, request):

        ofertas_pro = Oferta_Producto.objects.filter(estado=1, fk_oferta__fecha__gte=datetime.date.today()).values('fk_producto', 'fk_producto__nombre', 'fk_producto__imagen').annotate(
            preMin=Min('precioProvedor'), preMax=Max('precioProvedor'), canAceptada=Sum('cantidad_aceptada')).distinct()
        #print(aqui)
        return render(request, 'Administrador/catalogo.html', {'ofertas_pro':ofertas_pro})
