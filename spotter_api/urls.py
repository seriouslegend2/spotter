from django.urls import path

from routes.views import route_view


urlpatterns = [path("api/route/", route_view, name="route")]
