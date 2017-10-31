# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
import json
from django.db.models import Sum, Min, Max, QuerySet
from django.shortcuts import render, redirect, reverse
from django.views import View
from MarketPlace.models import Oferta_Producto, Catalogo, Producto, Pedido, PedidoProducto, Catalogo_Producto, \
    Productor, Oferta, Cooperativa, Semana
from Administrador.utils import catalogo_actual
    Productor, Oferta, Cooperativa, Semana
from Administrador.utils import catalogo_actual, catalogo_validaciones
from django.contrib import messages
from django.contrib.auth import authenticate, logout, login
from MarketPlace.utils import es_administrador, redirect_user_to_home


class AbstractAdministradorLoggedView(View):
    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            if es_administrador(self.request.user):
                return super(AbstractAdministradorLoggedView, self).dispatch(*args, **kwargs)
            else:
                return redirect_user_to_home(self.request)
        else:
            return redirect(reverse('administrador:ingresar'))


class Ingresar(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect(reverse('administrador:index'))
        else:
            return render(request, 'Administrador/ingresar.html', {})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect(reverse('administrador:index'))
        else:
            username = request.POST.get('username', '')
            password = request.POST.get('password', '')
            user = authenticate(username=username, password=password)
            if user is not None and es_administrador(user):
                login(request, user)
                return redirect(reverse('administrador:index'))
            else:
                messages.add_message(request, messages.ERROR, 'Por favor verifica tu usuario y contraseña')
                return render(request, 'Administrador/ingresar.html', {})


class Logout(View):
    def get(self, request):
        logout(request)
        return redirect(reverse('administrador:ingresar'))


class Index(AbstractAdministradorLoggedView):
    def get(self, request):
        return render(request, 'Administrador/index.html', {})


class CatalogoView(AbstractAdministradorLoggedView):
    def get(self, request):
        dia_semana = datetime.date.today().weekday()
        oferta_nueva = False
        info_catalogo = {}

        # Se valida que exista por lo menos una cooperativa.
        cooperativa = Cooperativa.objects.first()
        if not (cooperativa is None):
            # Se valida que sea domingo para permitir crear el catalogo.
            if dia_semana < 7:   # Se hace que la validacion siempre sea verdadera para que puedan realizar purebas
                # Se valida que no se haya creado ya un catalogo para la semana.
                catalogo = Catalogo.objects.filter(fecha_creacion__gte=datetime.date.today()).first()
                if catalogo is None:
                    # Se obtienen las ofertas agrupadas por producto (cantidad, precio minimo y maximo)
                    # Solo se toman las ofertas de los 3 dias anteriores(jueves, viernes, sabado)
                    ofertas_pro = Oferta_Producto \
                        .objects.filter(estado=1, fk_oferta__fecha__gte=datetime.date.today() + datetime.timedelta(days=-3)) \
                        .values('fk_producto', 'fk_producto__nombre', 'fk_producto__imagen', 'fk_producto__unidad_medida') \
                        .annotate(preMin=Min('precioProvedor'), preMax=Max('precioProvedor'),
                                  canAceptada=Sum('cantidad_aceptada')) \
                        .distinct()

                    oferta_nueva = ofertas_pro.count() > 0

                    if oferta_nueva:
                        subtitulo = datetime.date.today().strftime("%d/%m/%y")
                    else:
                        subtitulo = "No hay ofertas disponibles para crear el catálogo"

                    info_catalogo.update({'ofertas_pro': ofertas_pro, 'subtitulo': subtitulo})
                else:
                    # Se muestra el catalogo ya creado.
                    info_catalogo = catalogo_actual()
            else:
                # Si no es domingo se muestra el ultimo catalogo que se haya creado.
                info_catalogo = catalogo_actual()
        else:
            info_catalogo.update({'ofertas_pro':[], 'subtitulo': 'No hay cooperativas registradas en el sistema!'})

        return render(request, 'Administrador/catalogo.html',
                      {'ofertas_pro': info_catalogo['ofertas_pro'],
                       'subtitulo': info_catalogo['subtitulo'],
                       'oferta_nueva': oferta_nueva})

    def post(self, request):
        # Se carga la información desde el JSON recibido donde viene el id del producto con su respectivo precio.
        precios_recibidos = json.loads(request.POST.get('precios_enviar'))

        # Se crea el catalogo
        fecha_cierre = datetime.date.today() + datetime.timedelta(days=3)
        catalogo = Catalogo.objects.create(fecha_cierre=fecha_cierre)
        catalogo.save()

        # Se agregan los  productos al catalogo
        for item in precios_recibidos:
            Catalogo_Producto.objects.create(fk_catalogo=catalogo,
                                             fk_producto=Producto(id=item['producto']),
                                             precio=item['precio'])

        # Se carga la informacion del catalogo creado
        info_catalogo = catalogo_actual()
        subtitulo = "Catálogo creado correctamente!\r\n" + info_catalogo['subtitulo']

        return render(request, 'Administrador/catalogo.html', {
            'ofertas_pro': info_catalogo['ofertas_pro'],
            'subtitulo': subtitulo,
            'oferta_nueva': False
        })


class PedidosView(AbstractAdministradorLoggedView):
    def get(self, request):
        return render(request, 'Administrador/pedidos.html', {'pedidos': Pedido.objects.all()})

    def post(self, request):
        if request.POST.get('fecha_inicio', '') == '':
            fecha_inicio = datetime.datetime.now()
            fecha_fin = datetime.datetime.now()
            pedidos = Pedido.objects.filter(fecha_pedido__gte=fecha_inicio, fecha_pedido__lte=fecha_fin)
        else:
            fecha_inicio = request.POST.get('fecha_inicio', '')
            fecha_fin = request.POST.get('fecha_fin', '')
            pedidos = Pedido.objects.filter(fecha_pedido__gte=fecha_inicio, fecha_pedido__lte=fecha_fin)

        return render(request, 'Administrador/pedidos.html', {'pedidos': pedidos})


class DetallePedidoView(AbstractAdministradorLoggedView):
    def get(self, request, id_pedido):
        detalle_pedido = PedidoProducto.objects.filter(fk_pedido=id_pedido)
        pedido = Pedido.objects.get(id=id_pedido)
        if pedido.estado != 'PE':
            disable_button = 'disabled'
        else:
            disable_button = ''
        return render(request, 'Administrador/detalle-pedido.html', {
            'detalle_pedido': detalle_pedido,
            'id_pedido': id_pedido,
            'disable_button': disable_button
        })


class ActualizarEstadoPedidoView(AbstractAdministradorLoggedView):
    def post(self, request):
        id_pedido = request.POST.get('id_pedido', '0')
        pedido = Pedido.objects.get(id=id_pedido)
        pedido.estado = 'EC'
        pedido.save()
        return render(request, 'Administrador/pedidos.html', {'pedidos': Pedido.objects.all()})


class ListarOfertasView(AbstractAdministradorLoggedView):
    def get(self, request):
        ofertas = list()
        cantidad_ofertas = 0
        id_oferta = 0
        for productor in Productor.objects.all():
            for oferta in Oferta.objects.filter(fk_productor=productor.id):
                cantidad_ofertas = Oferta_Producto.objects.filter(fk_oferta=oferta.id).count()
                id_oferta = oferta.id
            ofertas.append((productor.nombre, cantidad_ofertas, id_oferta))

        return render(request, 'Administrador/ofertas.html', {'ofertas': ofertas})


class DetalleOfertaView(AbstractAdministradorLoggedView):
    def get(self, request, id_oferta, guardado_exitoso):
        ofertas_producto = Oferta_Producto.cargar_ofertas(id_oferta)

        return render(request, 'Administrador/detalle-oferta.html', {
            'ofertas_producto': ofertas_producto,
            'id_oferta': id_oferta,
            'guardado_exitoso': guardado_exitoso
        })


class RealizarOfertaView(AbstractAdministradorLoggedView):
    def post(self, request):
        id_oferta = request.POST.get('id_oferta')
        id_oferta_producto = request.POST.get('id_oferta_producto')
        aprobar = request.POST.get('aprobar')
        cantidad_aceptada = request.POST.get('cantidad_aceptada')
        if aprobar == '0' and cantidad_aceptada > 0:
            cantidad_aceptada = 0
        oferta_producto = Oferta_Producto.objects.get(pk=id_oferta_producto)
        oferta_producto.estado = aprobar
        oferta_producto.cantidad_aceptada = cantidad_aceptada
        oferta_producto.save()
        return redirect('administrador:detalle-ofertas', id_oferta=id_oferta, guardado_exitoso=1)

class Informes(View):
    def get(self, request):
        return render(request, 'Administrador/Informes/index.html', {})

class seleccionSemanas(View):
    def get(self, request):
        semanasAll= Semana.objects.all()
        semanasCount=len(semanasAll)
        semanas =[]
        if semanasCount >= 4:
            semanas.append((semanasAll[semanasCount-1]))
            semanas.append((semanasAll[semanasCount-2]))
            semanas.append((semanasAll[semanasCount-3]))
            semanas.append((semanasAll[semanasCount-4]))
        else:
            semanas=semanasAll
        return render(request, 'Administrador/Informes/seleccionSemanas.html',
                      {'semanas':semanas})

class listarMejoresProductos(View):
    def post(self,request):
        """   semanas = request.POST.getlist('semana',[])
   catalogos=[]
   catalogosProductosAll=[]
   pedidoProductoAll=[]
   for sem in semanas:
       catalogoSem=Catalogo.objects.filter(fk_semana=sem)
       catalogos.append(catalogoSem)
   for cat in catalogos:
       cataloProductos=Catalogo_Producto.objects.filter(fk_catalogo=cat)
       catalogosProductosAll.append(cataloProductos)
   for catProd in catalogosProductosAll:
       pedidoProducto=PedidoProducto.objects.filter(catProd)
       pedidoProductoAll.append(pedidoProducto)
       pedidoProductoAll"""
        return render(request, 'Administrador/Informes/mejoresProductos.html')

class InformesClientesMasRentables(View):
    def get(self, request):
        return render(request, 'Administrador/Informes/clientes_mas_rentables.html', {})
