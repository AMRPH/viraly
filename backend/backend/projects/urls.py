from django.urls import path
from .views import (
    FileUploadView,
    CreateProjectAPIView,
    GetProjectsAPIView,
    GetProjectAPIView,
    DeleteProjectAPIView,
    GetProjectVideoAPIView,
)


urlpatterns = [
    path('create/', CreateProjectAPIView.as_view()),
    path('upload/', FileUploadView.as_view()),

    path('', GetProjectsAPIView.as_view()),
    path('<int:pk>/', GetProjectAPIView.as_view()),
    path('<int:pk>/video/', GetProjectVideoAPIView.as_view()),
    path('delete/', DeleteProjectAPIView.as_view()),
]