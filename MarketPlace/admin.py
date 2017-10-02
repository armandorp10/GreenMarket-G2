# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin

# Register your models here.
from MarketPlace.models import Categoria, Producto, Oferta, oferta_producto


class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    list_display_links = ('id', 'nombre')
    search_fields = ('nombre',)

class ProductoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    list_display_links = ('id', 'nombre')
    search_fields = ('nombre',)

class OfertaAdmin(admin.ModelAdmin):
    list_display = ('id', 'productor_id', 'fecha')
    list_display_links = ('id',)
    search_fields = ('nombre',)

class oferta_productoAdmin(admin.ModelAdmin):
    list_display = ('id', 'fk_oferta', 'fk_producto', 'estado', 'cantidad_aceptada', 'cantidad_vendida', 'precio')
    list_display_links = ('id',)
    search_fields = ('estado',)

admin.site.register(Categoria, CategoriaAdmin)
admin.site.register(Producto, ProductoAdmin)
admin.site.register(Oferta, OfertaAdmin)
admin.site.register(oferta_producto, oferta_productoAdmin)
