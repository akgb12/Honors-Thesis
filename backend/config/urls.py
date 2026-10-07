from django.urls import path
from ninja import NinjaAPI

from projects.api import router

api = NinjaAPI(title="Honors Thesis Accessibility API", version="1.0.0")
api.add_router("", router)

urlpatterns = [
    path("api/", api.urls),
]
