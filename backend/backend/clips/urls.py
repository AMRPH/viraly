from django.urls import path
from .views import (
    GetClipsAPIView,
    GetClipsByProjectAPIView,
    GetClipAPIView,
    DeleteClipAPIView,
    GetClipVideoAPIView,
    PreRenderClipAPIView,
    RenderClipAPIView,
    GetRenderedClipVideoAPIView
)


urlpatterns = [
    path('', GetClipsAPIView.as_view()),
    path('<int:pk>/', GetClipAPIView.as_view()),
    path('<int:pk>/video/', GetClipVideoAPIView.as_view()),
    path('<int:pk>/rendered/video/', GetRenderedClipVideoAPIView.as_view()),
    path('clips/delete/', DeleteClipAPIView.as_view()),
    
    path('by_project/<int:project_id>/', GetClipsByProjectAPIView.as_view()),
    path('pre_render/', PreRenderClipAPIView.as_view()),
    path('render/', RenderClipAPIView.as_view()),
]