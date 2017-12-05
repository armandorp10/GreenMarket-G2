# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from math import radians, sin, cos, atan2, sqrt

from django.shortcuts import render, redirect, reverse, render_to_response
from django.utils.translation.trans_real import catalog
from django.views import View
from django.contrib import messages
from operator import itemgetter
from Administrador.utils import calcular_promedio
from Administrador.views import AbstractAdministradorLoggedView
from Cliente.forms import ClientForm, PaymentForm
from Cliente.models import Ciudad, Departamento
from MarketPlace.models import Cliente, Catalogo_Producto, Categoria, Cooperativa, Pedido, PedidoProducto, \
    Oferta_Producto, Catalogo, Canasta, Favorito, Productor, EvaluacionProducto, Producto, PedidoCanasta, ClienteProducto
from django.contrib.auth.models import User
from datetime import datetime
from django.db.models import F
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from MarketPlace.utils import es_cliente, redirect_user_to_home, es_productor, get_or_create_week, \
    formatear_lista_productos, get_id_cooperativa_global, formatear_lista_canastas, cantidad_disponible_canasta, cantidad_disponible_producto_catalogo, get_cooperativa_cliente, set_cooperativa_cliente
from django.contrib.auth import logout, login, authenticate
from django.db.transaction import atomic, savepoint, savepoint_commit, savepoint_rollback
from Cliente.utils import agregar_producto_carrito, agregar_canasta_carrito, get_or_create_cart, actualizar_inventario
from django.http import JsonResponse


class AbstractClienteLoggedView(View):
    logged_out_message = 'Por favor ingresa para acceder a ésta página'

    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            if es_cliente(self.request.user):
                return super(AbstractClienteLoggedView, self).dispatch(*args, **kwargs)
            else:
                rol = 'productor' if es_productor(self.request.user) else 'administrador'
                messages.add_message(
                    self.request,
                    messages.INFO,
                    'Para acceder a las funcionalidades de cliente, por favor salga de su cuenta de {rol}'
                        .format(rol=rol)
                )
                return redirect_user_to_home(self.request)
        else:
            messages.add_message(self.request, messages.INFO, self.logged_out_message)
            return redirect(reverse('cliente:index'))


class Ingresar(View):
    def post(self, request):
        if request.user.is_authenticated:
            return redirect(self.request.META.get('HTTP_REFERER', reverse('cliente:index')))
        else:
            username = request.POST.get('username', '')
            password = request.POST.get('password', '')
            user = authenticate(username=username, password=password)
            if user is not None and es_cliente(user):
                login(request, user)
                return redirect(self.request.META.get('HTTP_REFERER', reverse('cliente:index')))
            else:
                messages.add_message(request, messages.ERROR, 'Por favor verifica tu usuario y contraseña')
                return redirect(self.request.META.get('HTTP_REFERER', reverse('cliente:index')))


class Logout(View):
    def get(self, request):
        request.session['cooperativa'] = ''
        request.session['cart'] = ''
        logout(request)
        return redirect(reverse('cliente:index'))


class Index(View):
    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated and not es_cliente(self.request.user):
            rol = 'productor' if es_productor(self.request.user) else 'administrador'
            messages.add_message(
                self.request,
                messages.INFO,
                'Para acceder a las funcionalidades de cliente, por favor salga de su cuenta de {rol}'
                    .format(rol=rol)
            )
            return redirect_user_to_home(self.request)
        else:
            return super(Index, self).dispatch(*args, **kwargs)

    def get(self, request):
        cooperativas = Cooperativa.objects.all()
        cooperativa_id = get_cooperativa_cliente(request)
        catalogo = Catalogo.objects.filter(fk_semana=get_or_create_week(),
                                           fk_cooperativa_id=cooperativa_id)

        producto_catalogo = Catalogo_Producto.objects \
            .filter(fk_catalogo=catalogo).order_by('fk_producto__nombre')
        categorias = Categoria.objects.all()

        productos = formatear_lista_productos(producto_catalogo, request, cooperativa_id)

        return render(request, 'Cliente/index.html', {
            'productos_json': json.dumps(productos),
            'productos_catalogo': producto_catalogo,
            'categorias': categorias,
            'cooperativas': cooperativas,
            'solo_favoritos': False,
            'cooperativaSeleccionada': get_cooperativa_cliente(request),
            'buscarGeolocation':1
        })

    def post(self, request):
        # Se listan los productos por Cooperativa y se ordenan segun filtro
        cooperativa_id = request.POST.get('cooperativa_id', '')

        set_cooperativa_cliente(request, cooperativa_id)

        catalogo = Catalogo.objects.filter(fk_semana=get_or_create_week(), fk_cooperativa_id=cooperativa_id)

        producto_catalogo = Catalogo_Producto.objects.filter(fk_catalogo=catalogo).order_by('fk_producto__nombre')

        categorias = Categoria.objects.all()

        cooperativas = Cooperativa.objects.all()

        productos = formatear_lista_productos(producto_catalogo, request, int(cooperativa_id))

        mensaje= ''
        if len(productos) == 0:
            mensaje = 'La cooperativa seleccionada no cuenta con productos disponibles por el momento.'

        return render(request, 'Cliente/index.html', {
            'productos_json': json.dumps(productos),
            'categorias': categorias,
            'cooperativas': cooperativas,
            'mensajePython': mensaje,
            'cooperativaSeleccionada': get_cooperativa_cliente(request),
            'buscarGeolocation':0
        })


class Checkout(AbstractClienteLoggedView):
    logged_out_message = 'Por favor ingresa a tu cuenta para ir al checkout'

    def get(self, request):
        # Obtenemos el carrito y sus items
        # Si no encontramos nada, redirijimos el usuario al home y le notificamos que no tiene items en el carrito
        # De lo contrario mostramos la página de checkout
        cart = get_or_create_cart(request)
        items = cart.get('items', [])
        canastas = cart.get('canastas', [])

        if len(items) == 0 and len(canastas) == 0:
            messages.add_message(request, messages.WARNING, 'No tienes productos en tu carrito de compras')
            return redirect(reverse('cliente:index'))
        else:
            return render(request, 'Cliente/checkout/checkout.html', {})


class UpdateShoppingCart(AbstractClienteLoggedView):
    logged_out_message = 'Por favor ingresa a tu cuenta para agregar items a tu carrito'

    def post(self, request):
        # Se añade un nuevo item al carrito de compras (almacenado en la sesión) y se le notifica al usuario
        # Se retorna a la página desde el que se añadió el producto al carrito

        json_body = json.loads(request.body.decode('utf-8'))
        product_id = json_body.get('product_id', 0)
        quantity = json_body.get('quantity', 0)

        if product_id > 0 and quantity != 0:
            request.session['cart'] = agregar_producto_carrito(
                request=request,
                product_id=product_id,
                quantity=quantity
            )
            # messages.add_message(request, messages.SUCCESS, 'El producto se agregó al carrito satisfactoriamente')
        return JsonResponse(request.session['cart'])
        # return redirect(request.META.get('HTTP_REFERER', '/'))


class DeleteProductFromShoppingCart(AbstractClienteLoggedView):
    logged_out_message = 'Por favor ingresa a tu cuenta para poder eliminar items a tu carrito'

    def post(self, request):
        # Eliminamos el producto con el id dado del carrito de compras
        cart = get_or_create_cart(request)
        json_body = json.loads(request.body.decode('utf-8'))
        product_id = json_body.get('product_id', -1)

        items = cart.get('items', [])
        index = -1
        i = 0
        while i < len(items) and index == -1:
            item = items[i]
            if item['product_id'] == product_id:
                index = i
            i += 1

        if index >= 0:
            items.remove(items[index])
            cart['items'] = items
            request.session['cart'] = cart
        return JsonResponse(request.session['cart'])


@method_decorator(csrf_exempt, name='dispatch')
class RegisterClientView(View):
    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            return redirect_user_to_home(self.request)
        else:
            return super(RegisterClientView, self).dispatch(*args, **kwargs)

    def get(self, request):
        ciudades = Ciudad.get_all_ciudades()
        departamentos = Departamento.get_all_departamentos()
        return render(request, 'Cliente/registrar_cliente.html',
                      {'form': ClientForm(), 'ciudades': ciudades, 'departamentos': departamentos})

    def post(self, request):
        form = ClientForm(request.POST)
        if form.is_valid():
            cleaned_data = form.cleaned_data
            nombre = cleaned_data.get('nombre')
            apellido = cleaned_data.get('apellido')
            contrasena = cleaned_data.get('contrasena')

            ciudad = cleaned_data.get('ciudad')
            departamento = cleaned_data.get('departamento')
            telefono_contacto = cleaned_data.get('telefono_contacto')
            correo = cleaned_data.get('correo')
            direccion = cleaned_data.get('direccion')
            numero_identificacion = cleaned_data.get('numero_identificacion')
            tipo_identificacion = cleaned_data.get('tipo_identificacion')
            user_model = User.objects.create_user(
                username=correo,
                password=contrasena,
                first_name=nombre,
                last_name=apellido,
                email=correo
            )
            user_model.save()
            cliente_model = Cliente(
                fk_django_user=user_model,
                ciudad=ciudad,
                departamento=departamento,
                telefono_contacto=telefono_contacto,
                direccion=direccion,
                numero_identificacion=numero_identificacion,
                tipo_identificacion=tipo_identificacion
            )
            cliente_model.save()
            messages.add_message(
                request,
                messages.SUCCESS,
                'Tu cuenta fue creada exitosamente, ya puedes ingresar a Green Market'
            )
            return redirect(reverse('cliente:registrar-cliente'))
        else:
            return render_to_response('Cliente/registrar_cliente.html', {'form': form})


class MisPedidosView(AbstractClienteLoggedView):
    logged_out_message = 'Por favor ingresa a tu cuenta para poder ver tus pedidos'

    def get(self, request):
        cliente = Cliente.objects.filter(fk_django_user_id=request.user.id).first()
        pedidos_cliente = Pedido.objects.filter(fk_cliente=cliente)
        return render(request, 'Cliente/mis_pedidos.html', {
            'pedidos_entregados': pedidos_cliente.filter(estado='EN'),
            'pedidos_por_entregar': pedidos_cliente.filter(estado__in=('PE', 'EC'))
        })


@method_decorator(csrf_exempt, name='dispatch')
class DoPayment(AbstractClienteLoggedView):
    logged_out_message = 'Por favor ingresa a tu cuenta para realizar el pago de tu pedido'

    def get(self, request):
        return render(request, 'Cliente/checkout/checkout.html', {'form': PaymentForm()})

    @atomic
    def post(self, request):
        checkout_Json = json.loads(request.POST.get('checkout_form'))
        detalles_productos = checkout_Json.get('detalles_productos')
        detalles_canastas = checkout_Json.get('detalles_canastas')
        informacion_envio = checkout_Json.get('informacion_envio')
        informacion_pago = checkout_Json.get('informacion_pago')
        nombre_envio = informacion_envio.get('nombre')
        direccion_envio = informacion_envio.get('direccion')
        email_envio = informacion_envio.get('email')
        celular_envio = informacion_envio.get('celular')
        telefono_envio = informacion_envio.get('telefono')
        observaciones_envio = informacion_envio.get('observaciones')
        nombre_pago = informacion_pago.get('nombre_completo')
        numero_identificacion = informacion_pago.get('numero_documento')
        tipo_identificacion = informacion_pago.get('tipo_documento')

        cliente_model = Cliente.objects.filter(fk_django_user_id=request.user.id).first()
        pedido_model = Pedido(
            fk_cliente=cliente_model,
            fecha_pedido=datetime.now(),
            fecha_entrega=datetime.now(),
            estado='PE',
            valor_total=0,
            nombre_envio=nombre_envio,
            direccion_envio=direccion_envio,
            email_envio=email_envio,
            telefono_envio=telefono_envio,
            observaciones_envio=observaciones_envio,
            nombre_pago=nombre_pago,
            tipo_identificacion=tipo_identificacion,
            numero_identificacion=numero_identificacion
        )
        checkpoint = savepoint()
        pedido_model.save()
        id_cooperativa = get_id_cooperativa_global(request)
        valor_total = 0
        for item in detalles_productos:
            producto_catalogo = Catalogo_Producto.objects.get(
                fk_producto_id=item.get('product_id'),
                fk_catalogo__fk_cooperativa_id=id_cooperativa,
                fk_catalogo__fk_semana=get_or_create_week()
            )
            cantidad = int(item.get('quantity'))
            pedido_producto_model = PedidoProducto(
                fk_catalogo_producto=producto_catalogo,
                fk_pedido=pedido_model,
                cantidad=cantidad,
                fk_oferta_producto=Oferta_Producto.objects.filter(
                    fk_producto=producto_catalogo.fk_producto,
                    fk_oferta__fk_semana=get_or_create_week(),
                    estado=1).first()
            )
            pedido_producto_model.save()

            cliente_producto_model = ClienteProducto.objects.filter(fk_producto=producto_catalogo.fk_producto,
                                                                    fk_cliente=cliente_model)
            if cliente_producto_model.exists():
                total_cantidad = cliente_producto_model[0].cantidad + cantidad
                total_frecuencia = cliente_producto_model[0].frecuencia + 1
                cliente_producto_model.update(cantidad=total_cantidad, frecuencia=total_frecuencia)
            else:
                cliente_producto_model = ClienteProducto(
                    fk_cliente=cliente_model,
                    fk_producto=producto_catalogo.fk_producto,
                    fk_semana=get_or_create_week(),
                    cantidad=cantidad,
                    frecuencia=1,
                    sugerir=False
                )
                cliente_producto_model.save()

            cantidad_restante = actualizar_inventario(producto_catalogo, cantidad, get_id_cooperativa_global(request))

            if cantidad_restante > 0:
                cart = get_or_create_cart(request)

                items = cart.get('items', [])
                cart['items'] = list(filter(lambda x: x['product_id'] != producto_catalogo.fk_producto_id, items))
                request.session['cart'] = cart
                messages.add_message(
                    request,
                    messages.ERROR,
                    'El producto {producto} ya no se encuentra disponible'.format(
                        producto=producto_catalogo.fk_producto.nombre)
                )
                savepoint_rollback(checkpoint)
                return redirect(reverse('cliente:checkout'))
            else:
                valor_total += producto_catalogo.precio * cantidad

        canastas_query = Canasta.objects.filter(
            esta_publicada=True,
            fk_semana=get_or_create_week(),
            fk_cooperativa_id=get_id_cooperativa_global(request)
        )
        for canasta_carrito in detalles_canastas:
            canasta = canastas_query.get(id=canasta_carrito.get('canasta_id'))
            cantidad_canasta = int(canasta_carrito.get('quantity'))
            pedido_canasta_model = PedidoCanasta(
                cantidad=cantidad_canasta,
                fk_pedido=pedido_model,
                fk_canasta=canasta,
            )
            for canasta_producto in canasta.productos:
                producto_catalogo = canasta_producto.fk_producto_catalogo
                cantidad_producto = canasta_producto.cantidad * cantidad_canasta
                cantidad_restante = actualizar_inventario(producto_catalogo, cantidad_producto,
                                                          get_id_cooperativa_global(request))
                if cantidad_restante > 0:
                    cart = get_or_create_cart(request)
                    canastas_carrito = cart.get('canastas', [])
                    cart['canastas'] = list(filter(lambda x: x['canasta_id'] != canasta.id, canastas_carrito))
                    request.session['cart'] = cart
                    messages.add_message(
                        request,
                        messages.ERROR,
                        'La canasta {canasta} ya no se encuentra disponible'.format(canasta=canasta.nombre)
                    )
                    savepoint_rollback(checkpoint)
                    return redirect(reverse('cliente:checkout'))

            valor_total += canasta.precio * cantidad_canasta
            pedido_canasta_model.save()



        pedido_model.valor_total = valor_total
        pedido_model.save()
        savepoint_commit(checkpoint)
        request.session['cart'] = ""
        messages.add_message(
            request,
            messages.SUCCESS,
            'La compra se realizó exitosamente'
        )
        return redirect(reverse('cliente:detalle-mis-pedidos', kwargs={'id_pedido': pedido_model.id}))


class Canastas(View):
    def get(self, request):
        canastas = Canasta.objects.filter(
            esta_publicada=True,
            fk_semana=get_or_create_week(),
            fk_cooperativa_id=get_id_cooperativa_global(request)
        )
        if canastas:
            arreglo_canastas = formatear_lista_canastas(canastas, get_id_cooperativa_global(request))
            return render(request, 'Cliente/canastas.html', {
                'canastas_json': json.dumps(arreglo_canastas)
            })
        else:
            messages.add_message(request, messages.INFO, 'Actualmente no hay canastas disponibles')
            return redirect(reverse('cliente:index'))


class AgregarCanastaCarrito(AbstractClienteLoggedView):
    @atomic
    def post(self, request):
        body = json.loads(request.body.decode('utf-8'))
        id_canasta = body.get('id_canasta', 0)
        quantity = body.get('quantity', 0)
        canasta = Canasta.objects.filter(id=id_canasta, esta_publicada=True, fk_semana=get_or_create_week()).first()
        if canasta and quantity > 0:
            request.session['cart'] = agregar_canasta_carrito(request, id_canasta, quantity)
            return JsonResponse(request.session['cart'])
        else:
            return JsonResponse({'status': 'error'}, status=500)


class ActualizarCanastaCarritoCompras(AbstractClienteLoggedView):
    def post(self, request):

        json_body = json.loads(request.body.decode('utf-8'))
        canasta_id = json_body.get('canasta_id', 0)
        quantity = json_body.get('quantity', 0)

        if canasta_id > 0 and quantity != 0:
            request.session['cart'] = agregar_canasta_carrito(
                request=request,
                canasta_id=canasta_id,
                quantity=quantity
            )
            # messages.add_message(request, messages.SUCCESS, 'El producto se agregó al carrito satisfactoriamente')
        return JsonResponse(request.session['cart'])
        # return redirect(request.META.get('HTTP_REFERER', '/'))


class EliminarCanastaCarritoCompras(AbstractClienteLoggedView):
    def post(self, request):
        cart = get_or_create_cart(request)
        json_body = json.loads(request.body.decode('utf-8'))
        canasta_id = json_body.get('canasta_id', -1)

        canastas = cart.get('canastas', [])
        index = -1
        i = 0
        while i < len(canastas) and index == -1:
            item = canastas[i]
            if item['id'] == canasta_id:
                index = i
            i += 1

        if index >= 0:
            canastas.remove(canastas[index])
            cart['canastas'] = canastas
            request.session['cart'] = cart
        return JsonResponse(request.session['cart'])


class AgregarProductoFavoritoView(AbstractClienteLoggedView):
    def post(self, request):
        try:
            body_unicode = request.body.decode('utf-8')
            body = json.loads(body_unicode)
            id_producto = body.get('id_producto', '0')
            cliente = Cliente.objects.filter(fk_django_user_id=request.user.id).first()
            exist = Favorito.objects.filter(fk_producto_id=int(id_producto), fk_cliente_id=cliente.id).exists()
            if not exist:
                favorito = Favorito(fk_producto_id=int(id_producto), fk_cliente_id=cliente.id)
                favorito.save()
            return JsonResponse({"Mensaje": "OK"})
        except:
            return JsonResponse({"Mensaje": "Fallo"}, status=500)


class EliminarFavoritoView(AbstractClienteLoggedView):
    def post(self, request):
        try:
            body_unicode = request.body.decode('utf-8')
            body = json.loads(body_unicode)
            id_producto = body.get('id_producto', '0')
            user_id = request.user.id
            favorito = Favorito.objects.filter(fk_producto_id=int(id_producto), fk_cliente__fk_django_user_id=user_id)
            favorito.delete()
            return JsonResponse({"Mensaje": "OK"})
        except:
            return JsonResponse({"Mensaje": "Fallo"}, status=500)


class DetalleMisPedidoView(AbstractClienteLoggedView):
    def get(self, request, id_pedido):
        pedido = Pedido.objects.get(id=id_pedido)
        detalle_mi_pedido = PedidoProducto.objects.filter(fk_pedido_id=id_pedido)
        lista_productos = []
        for detPed in detalle_mi_pedido:
            productoPedido = detPed
            valor = detPed.cantidad * detPed.fk_catalogo_producto.precio
            categoria = detPed.fk_catalogo_producto.fk_producto.fk_categoria.nombre
            evalProducto = EvaluacionProducto.objects.filter(fk_pedido_producto_id=productoPedido.id)
            if len(evalProducto) == 0:
                disable_button_producto = ''
            else:
                disable_button_producto = 'disabled'
            lista_productos.append({
                'categoria': categoria,
                'producto': productoPedido,
                'valor': valor,
                'disable_button_producto': disable_button_producto
            })

        pedido_canastas = PedidoCanasta.objects.filter(fk_pedido_id=id_pedido)

        if pedido.estado != 'EN':
            disable_button = 'disabled'
        else:
            disable_button = ''

        return render(request, 'Cliente/detalle-mis-pedidos.html', {
            'detalle_pedido': lista_productos,
            'pedido_canastas': pedido_canastas,
            'pedido': pedido,
            'disable': disable_button
        })


class CalificarMisPedidoView(AbstractClienteLoggedView):
    def get(self, request, fk_pedido_producto, fk_productor, producto, pedido):
        productoSelected = Producto.objects.filter(id=producto).first
        return render(request, 'Cliente/calificar-mis-pedidos.html', {
            'producto': productoSelected,
            'fk_pedido_producto': fk_pedido_producto,
            'fk_productor': fk_productor,
            'pedido': pedido
        })


class InsertCalificacionProductoVew(AbstractClienteLoggedView):
    def post(self, request, pedido_producto, productor, id_pedido):
        productor = Productor.objects.filter(id=productor).first()
        pedidoProducto = PedidoProducto.objects.filter(id=pedido_producto).first()
        ValorCalificacion = request.POST.get('calificacion', '')
        evaluacion = EvaluacionProducto(fk_productor=productor, fk_pedido_producto=pedidoProducto,
                                        calificacion=ValorCalificacion)
        evaluacion.save()
        messages.add_message(
            request, messages.SUCCESS,
            'La calificacion fue guardada exitosamente'
        )
        return redirect(reverse('cliente:detalle-mis-pedidos', args=(id_pedido)))


class MejoresProductores(View):
    def get(self, request):
        productores_list = Productor.objects.all()
        respuesta = []
        promedio = 0.0
        productores_ordenado = []
        if len(productores_list) != 0:
            for prod_list in productores_list:
                promedio = calcular_promedio(prod_list)
                respuesta.append({
                    'productor': prod_list,
                    'calificacion': "{0:.4f}".format(promedio)
                })
            productores_ordenado = sorted(respuesta, key=itemgetter('calificacion'), reverse=True)
        else:
            messages.add_message(
                request, messages.SUCCESS,
                'No se encontraron productores'
            )
        return render(request, 'Cliente/mejoresProductores.html', {'datos': productores_ordenado})

@method_decorator(csrf_exempt, name='dispatch')
class getIdCooperativaByLocation(View):
    def get(self, request):
        return JsonResponse({})

    def post(self, request):
        body_unicode = request.body.decode('utf-8')
        body = json.loads(body_unicode)

        longitud = body["longitud"]
        latitud = body["latitud"]

        idCooperativa = self.get_coop_by_location(longitud,latitud)

        return JsonResponse({"idCooperativa": idCooperativa})

    def get_coop_by_location(self, long, lat):
        lat1 = radians(lat)
        lon1 = radians(long)
        distanciaMasCorta = 0
        coopId = 0
        # approximate radius of earth in km
        R = 6373.0

        cooperativas = Cooperativa.objects.all()

        for coop in cooperativas:
            coordenadas = coop.coordenadas_gps.split(',')
            lat2 = radians(float(coordenadas[0]))

            lon2 = radians(float(coordenadas[1]))

            dlon = lon2 - lon1
            dlat = lat2 - lat1

            a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            c = 2 * atan2(sqrt(a), sqrt(1 - a))

            distance = R * c

            if distanciaMasCorta == 0:
                distanciaMasCorta = distance
                coopId = coop.id
            else:
                if distance < distanciaMasCorta:
                    distanciaMasCorta = distance
                    coopId = coop.id

        return coopId
    
class ProductosSugeridos(View):
    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated and not es_cliente(self.request.user):
            rol = 'productor' if es_productor(self.request.user) else 'administrador'
            messages.add_message(
                self.request,
                messages.INFO,
                'Para acceder a las funcionalidades de cliente, por favor salga de su cuenta de {rol}'
                    .format(rol=rol)
            )
            return redirect_user_to_home(self.request)
        else:
            return super(ProductosSugeridos, self).dispatch(*args, **kwargs)

    def get(self, request):
        cooperativas = Cooperativa.objects.all()
        cooperativa_id = get_cooperativa_cliente(request)
        catalogo = Catalogo.objects.filter(fk_semana=get_or_create_week(),
                                           fk_cooperativa_id=cooperativa_id)

        cliente_model = Cliente.objects.filter(fk_django_user=self.request.user).first()
        cliente_producto = ClienteProducto.objects.filter(sugerir=True, fk_cliente=cliente_model).values('fk_producto_id')

        producto_catalogo = Catalogo_Producto.objects \
            .filter(fk_catalogo=catalogo, fk_producto_id__in=cliente_producto)
        categorias = Categoria.objects.all()

        productos = formatear_lista_productos(producto_catalogo, request, cooperativa_id)

        return render(request, 'Cliente/productos-sugeridos.html', {
            'productos_json': json.dumps(productos),
            'productos_catalogo': producto_catalogo,
            'categorias': categorias,
            'cooperativas': cooperativas,
            'solo_favoritos': False,
            'cooperativaSeleccionada': get_cooperativa_cliente(request),
            'buscarGeolocation':1
        })

    def post(self, request):
        # Se listan los productos por Cooperativa y se ordenan segun filtro
        cooperativa_id = request.POST.get('cooperativa_id', '')

        set_cooperativa_cliente(request, cooperativa_id)

        catalogo = Catalogo.objects.filter(fk_semana=get_or_create_week(), fk_cooperativa_id=cooperativa_id)

        cliente_model = Cliente.objects.filter(fk_django_user=self.request.user).first()
        cliente_producto = ClienteProducto.objects.filter(sugerir=True, fk_cliente=cliente_model).values('fk_producto_id')

        producto_catalogo = Catalogo_Producto.objects.filter(fk_catalogo=catalogo, fk_producto_id__in=cliente_producto)\
            .order_by('fk_producto__nombre')

        categorias = Categoria.objects.all()

        cooperativas = Cooperativa.objects.all()

        productos = formatear_lista_productos(producto_catalogo, request, int(cooperativa_id))

        mensaje= ''
        if len(productos) == 0:
            mensaje = 'La cooperativa seleccionada no cuenta con productos sugeridos para ti.'

        return render(request, 'Cliente/productos-sugeridos.html', {
            'productos_json': json.dumps(productos),
            'categorias': categorias,
            'cooperativas': cooperativas,
            'mensajePython': mensaje,
            'cooperativaSeleccionada': get_cooperativa_cliente(request),
            'buscarGeolocation':0
        })


