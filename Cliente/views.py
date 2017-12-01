# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.shortcuts import render, redirect, reverse, render_to_response
from django.views import View
from django.contrib import messages
from Cliente.forms import ClientForm, PaymentForm
from Cliente.models import Ciudad, Departamento
from MarketPlace.models import Cliente, Catalogo_Producto, Categoria, Cooperativa, Pedido, PedidoProducto, \
    Oferta_Producto, Catalogo, Canasta, CanastaProducto, Favorito
from django.contrib.auth.models import User
from datetime import datetime
from django.db.models import F
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from MarketPlace.utils import es_cliente, redirect_user_to_home, es_productor, get_or_create_week, cantidad_disponible_producto_catalogo
from django.contrib.auth import logout, login, authenticate
from django.db.transaction import atomic, savepoint, savepoint_commit, savepoint_rollback
from Cliente.utils import agregar_producto_carrito
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
        catalogo = Catalogo.objects.filter(fk_semana=get_or_create_week())
        producto_catalogo = Catalogo_Producto.objects \
            .filter(fk_catalogo__fk_semana__fk_cooperativa_id=cooperativas.first(), fk_catalogo=catalogo) \
            .order_by('fk_producto__nombre')
        categorias = Categoria.objects.all()

        productos = []
        for producto in producto_catalogo:
            cantidad_disponible = cantidad_disponible_producto_catalogo(producto)
            if cantidad_disponible > 0:
                product_dict = producto.to_dict
                product_dict['cantidad_disponible'] = cantidad_disponible
                productos.append(product_dict)

        return render(request, 'Cliente/index.html', {
            'productos_json': json.dumps(productos),
            'productos_catalogo': producto_catalogo,
            'categorias': categorias,
            'cooperativas': cooperativas,
        })

    def post(self, request):
        # Se listan los productos por Cooperativa y se ordenan segun filtro
        cooperativa_id = request.POST.get('cooperativa_id', '')
        ordenar_por = request.POST.get('ordenar', '')
        producto_catalogo = Catalogo_Producto.objects \
            .filter(fk_catalogo__fk_semana__fk_cooperativa__id=cooperativa_id) \
            .order_by(ordenar_por)
        categorias = Categoria.objects.all()
        cooperativas = Cooperativa.objects.all()

        return render(request, 'Cliente/index.html', {
            'productos_catalogo': producto_catalogo,
            'categorias': categorias,
            'cooperativas': cooperativas
        })


class Checkout(AbstractClienteLoggedView):
    logged_out_message = 'Por favor ingresa a tu cuenta para ir al checkout'

    def get(self, request):
        # Obtenemos el carrito y sus items
        # Si no encontramos nada, redirijimos el usuario al home y le notificamos que no tiene items en el carrito
        # De lo contrario mostramos la página de checkout
        cart = request.session.get('cart', None)
        items = []
        if cart:
            items = cart.get('items', [])

        if not cart or len(items) == 0:
            messages.add_message(request, messages.WARNING, 'No tienes productos en tu carrito de compras')
            return redirect(reverse('cliente:index'))
        else:
            return render(request, 'Cliente/checkout/checkout.html', {})


class UpdateShoppingCart(AbstractClienteLoggedView):
    logged_out_message = 'Por favor ingresa a tu cuenta para agregar items a tu carrito'

    def post(self, request):
        # Se añade un nuevo item al carrito de compras (almacenado en la sesión) y se le notifica al usuario
        # Se retorna a la página desde el que se añadió el producto al carrito

        json_body = json.loads(request.body)
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
        cart = request.session.get('cart', None)
        json_body = json.loads(request.body)
        product_id = json_body.get('product_id', -1)
        if cart:
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
            return render(request, 'Cliente/index.html', {})
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
        detalles_pedido = checkout_Json.get('detalles_pedido')
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

        valor_total = 0
        for item in detalles_pedido:
            producto_catalogo = Catalogo_Producto.objects.get(id=item.get('product_id'))
            cantidad = int(item.get('quantity'))
            pedido_producto_model = PedidoProducto(
                fk_catalogo_producto=producto_catalogo,
                fk_pedido=pedido_model,
                cantidad=cantidad
            )
            pedido_producto_model.save()
            valor_total += producto_catalogo.precio * cantidad
            cantidad_disponible = 0

            try:
                while cantidad != 0:
                    if cantidad_disponible > cantidad:
                        oferta_producto.cantidad_vendida = cantidad
                        oferta_producto.save()
                        cantidad = 0

                    elif cantidad_disponible > 0:
                        oferta_producto.cantidad_vendida = oferta_producto.cantidad_aceptada
                        oferta_producto.save()
                        cantidad = cantidad - cantidad_disponible
                    else:
                        oferta_producto = Oferta_Producto \
                            .objects.filter(fk_producto=producto_catalogo.fk_producto) \
                            .exclude(cantidad_vendida=F('cantidad_aceptada')) \
                            .order_by('precioProvedor').first()
                        cantidad_disponible = oferta_producto.cantidad_aceptada - oferta_producto.cantidad_vendida
            except:
                cart = request.session.get('cart', None)
                if cart:
                    items = cart.get('items', [])
                    cart['items'] = list(filter(lambda x: x['product_id'] != producto_catalogo.id, items))
                    request.session['cart'] = cart
                messages.add_message(
                    request,
                    messages.ERROR,
                    'El producto {producto} ya no se encuentra disponible'.format(producto=producto_catalogo.fk_producto.nombre)
                )
                savepoint_rollback(checkpoint)
                return redirect(reverse('cliente:checkout'))

        pedido_model.valor_total = valor_total
        pedido_model.save()
        savepoint_commit(checkpoint)

        request.session['cartCompra'] = request.session['cart']
        request.session['cart'] = ""
        return render(request, 'Cliente/checkout/detalle-compra-exitosa.html',
                      {'compra': True})


class Canastas(View):
    def get(self, request):
        canastas = Canasta.objects.filter(esta_publicada=True, fk_semana=get_or_create_week())
        if canastas:
            return render(request, 'Cliente/canastas.html', {'canastas': canastas})
        else:
            messages.add_message(request, messages.INFO, 'Actualmente no hay canastas disponibles')
            return redirect(reverse('cliente:index'))


class AgregarCanastaCarrito(AbstractClienteLoggedView):
    logged_out_message = 'Por favor ingresa a tu cuenta para agregar canastas a tu carrito'

    @atomic
    def post(self, request):
        id_canasta = request.POST.get('id_canasta', '0')
        canasta = Canasta.objects.filter(id=id_canasta, esta_publicada=True, fk_semana=get_or_create_week()).first()
        if canasta:
            productos_canasta = CanastaProducto.objects.filter(fk_canasta_id=canasta)
            for producto_canasta in productos_canasta:
                request.session['cart'] = agregar_producto_carrito(
                    request=request,
                    product_id=producto_canasta.fk_producto_catalogo_id,
                    quantity=producto_canasta.cantidad
                )

            messages.add_message(
                request,
                messages.SUCCESS,
                'Los productos de la canasta fueron añadidos al carrito'
            )
        else:
            messages.add_message(
                request,
                messages.ERROR,
                'La canasta que estas buscando ya no se encuentra disponible'
            )
        return redirect(reverse('cliente:canastas'))


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
