from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import FileResponse
import os
import re
import pysubs2

from .serializers import (
    CreateImageOverlaySerializer, CreateTextOverlaySerializer, CreateSubtitlesOverlaySerializer,
    ImageOverlaySerializer, TextOverlaySerializer, SubtitlesOverlaySerializer
)
from .models import TextOverlay, ImageOverlay, SubtitlesOverlay
from clips.models import Clip

import uuid
import mimetypes

FILES_DIR = getattr(settings, 'MEDIA_ROOT', 'files')


class UploadImage(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'No file provided.'}, status=400)

        ext = uploaded_file.name.split('.')[-1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            return Response({'error': 'Unsupported file format.'}, status=400)

        new_filename = f"{uuid.uuid4()}.{ext}"
        fs = FileSystemStorage(location=f'{FILES_DIR}/overlays/')
        filename = fs.save(new_filename, uploaded_file)
        return Response({'detail': 'Image uploaded', 'filename': filename}, status=201)


class CreateImageOverlay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateImageOverlaySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            overlay = serializer.save()
            return Response({"detail": ImageOverlaySerializer(overlay).data}, status=201)
        return Response({"error": serializer.errors}, status=400)


class EditImageOverlay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        overlay = get_object_or_404(ImageOverlay, pk=request.data.get('id'), user=request.user)
        serializer = ImageOverlaySerializer(overlay, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return Response({"detail": ImageOverlaySerializer(instance).data}, status=200)
        return Response({"error": serializer.errors}, status=400)


class DeleteImageOverlay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        overlay = get_object_or_404(ImageOverlay, pk=request.data.get('id'), user=request.user)

        if os.path.exists(f'{FILES_DIR}/overlays/{overlay.image_filename}'):
            os.remove(f'{FILES_DIR}/overlays/{overlay.image_filename}')
            
        overlay.delete()
        return Response({"detail": "ImageOverlay deleted"}, status=200)
    

class GetImageOverlayImage(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        overlay = get_object_or_404(ImageOverlay, pk=pk, user=request.user)
        output_path = f'{FILES_DIR}/overlays/{overlay.image_filename}'

        if not os.path.isfile(output_path):
            return Response({'error': 'Video file not found'}, status=404)

        _, ext = os.path.splitext(output_path)
        ext = ext.lstrip('.')
        content_type, _ = mimetypes.guess_type(output_path)
        
        return FileResponse(
            open(output_path, 'rb'),
            content_type=content_type or 'application/octet-stream',
            filename=f'project_{pk}.{ext}'
        )




class CreateTextOverlay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateTextOverlaySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            overlay = serializer.save()
            return Response({"detail": TextOverlaySerializer(overlay).data}, status=201)
        return Response({"error": serializer.errors}, status=400)


class EditTextOverlay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        overlay = get_object_or_404(TextOverlay, pk=request.data.get('id'), user=request.user)
        serializer = TextOverlaySerializer(overlay, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return Response({"detail": TextOverlaySerializer(instance).data})
        return Response({"error": serializer.errors}, status=400)


class DeleteTextOverlay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        overlay = get_object_or_404(TextOverlay, pk=request.data.get('id'), user=request.user)
        overlay.delete()
        return Response({"detail": "TextOverlay deleted"}, status=200)




class SubtitlesByClip(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, clip_id):
        clip = get_object_or_404(Clip, pk=clip_id, user=request.user)

        subs = pysubs2.load(f'{FILES_DIR}/sources/{clip.project.subtitles_filename}', encoding="utf-8")

        start_ms = int(clip.start * 1000)
        end_ms = int(clip.end * 1000)

        filtered_subs = []
        for event in subs.events:
            if event.end > start_ms and event.start < end_ms:
                text = event.text

                text = re.sub(r"\{.*?\}", "", text)  
                text = re.sub(r"<.*?>", "", text)  

                text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)

                filtered_subs.append({
                    "start": event.start / 1000,
                    "end": event.end / 1000,
                    "text": text.strip()
                })

        return Response({"detail": filtered_subs}, status=200)


class CreateSubtitlesOverlay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateSubtitlesOverlaySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            overlay = serializer.save()
            return Response({"detail": SubtitlesOverlaySerializer(overlay).data}, status=201)
        return Response({"error": serializer.errors}, status=400)


class EditSubtitlesOverlay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        overlay = get_object_or_404(SubtitlesOverlay, pk=request.data.get('id'), user=request.user)
        serializer = SubtitlesOverlaySerializer(overlay, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return Response({"detail": SubtitlesOverlaySerializer(instance).data})
        return Response({"error": serializer.errors}, status=400)


class DeleteSubtitlesOverlay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        overlay = get_object_or_404(SubtitlesOverlay, pk=request.data.get('id'), user=request.user)
        overlay.delete()
        return Response({"detail": "SubtitlesOverlay deleted"}, status=200)




class OverlaysByClip(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, clip_id):
        text_overlays = TextOverlay.objects.filter(clip_id=clip_id, user=request.user)
        image_overlays = ImageOverlay.objects.filter(clip_id=clip_id, user=request.user)
        subtitles_overlays = SubtitlesOverlay.objects.filter(clip_id=clip_id, user=request.user)

        return Response({
            "detail": {
                'text': TextOverlaySerializer(text_overlays, many=True).data,
                'image': ImageOverlaySerializer(image_overlays, many=True).data,
                'subtitles': SubtitlesOverlaySerializer(subtitles_overlays, many=True).data,
            }
        }, status=200)
