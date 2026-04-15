from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('api/admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/projects/', include('projects.urls')),
    path('api/clips/', include('clips.urls')),
    path('api/overlays/', include('overlays.urls')),
]
