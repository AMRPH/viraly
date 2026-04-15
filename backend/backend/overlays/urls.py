from django.urls import path
from .views import (
    UploadImage,
    CreateImageOverlay,
    EditImageOverlay,
    DeleteImageOverlay,
    CreateTextOverlay,
    EditTextOverlay,
    DeleteTextOverlay,
    OverlaysByClip,
    SubtitlesByClip,
    CreateSubtitlesOverlay,
    EditSubtitlesOverlay,
    DeleteSubtitlesOverlay,
    GetImageOverlayImage
)


urlpatterns = [
    path('image/upload/', UploadImage.as_view()),
    path('image/create/', CreateImageOverlay.as_view()),
    path('image/edit/', EditImageOverlay.as_view()),
    path('image/delete/', DeleteImageOverlay.as_view()),
    path('image/file/<int:pk>/', GetImageOverlayImage.as_view()),

    path('text/create/', CreateTextOverlay.as_view()),
    path('text/edit/', EditTextOverlay.as_view()),
    path('text/delete/', DeleteTextOverlay.as_view()),



    path('subtitles/create/', CreateSubtitlesOverlay.as_view()),
    path('subtitles/edit/', EditSubtitlesOverlay.as_view()),
    path('subtitles/delete/', DeleteSubtitlesOverlay.as_view()),
    path('subtitles/by_clip/<int:clip_id>/', SubtitlesByClip.as_view()),


    path('by_clip/<int:clip_id>/', OverlaysByClip.as_view()),
]