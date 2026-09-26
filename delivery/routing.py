from django.urls import path 
from . import consumers


websocket_urlpatterns = [
        path('ws/livestatus/<str:room_name>/', consumers.OrderConsumer.as_asgi()),
]