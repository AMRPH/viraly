# Внешние библиотеки DRF и Django
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import StreamingHttpResponse
from django.conf import settings

import os
import mimetypes
import re

from clips.serializers import ClipSerializer, PreRenderClipSerializer
from projects.models import Project
from clips.models import Clip
from overlays.models import TextOverlay, ImageOverlay, SubtitlesOverlay
from projects.tasks import pre_render_clip, render_clip

FILES_DIR = getattr(settings, 'MEDIA_ROOT', 'files')

class GetClipsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        clips = Clip.objects.filter(user=request.user)
        serializer = ClipSerializer(clips, many=True)
        return Response({'detail': serializer.data}, status=200)


class GetClipsByProjectAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id, user=request.user)
        clips = Clip.objects.filter(project=project)
        serializer = ClipSerializer(clips, many=True)
        return Response({'detail': serializer.data}, status=200)


class GetClipAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        clip = get_object_or_404(Clip, pk=pk, user=request.user)
        serializer = ClipSerializer(clip)
        return Response({'detail': serializer.data}, status=200)


class GetClipVideoAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        clip = get_object_or_404(Clip, pk=pk)
        output_path = f'{FILES_DIR}/clips/{clip.video_filename}'

        if not os.path.isfile(output_path):
            return Response({'error': 'Video file not found'}, status=404)

        file_size = os.path.getsize(output_path)
        content_type, _ = mimetypes.guess_type(output_path)
        content_type = content_type or 'application/octet-stream'

        range_header = request.headers.get('Range', '').strip()
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)

        if range_match:
            start = int(range_match.group(1))
            end = range_match.group(2)
            end = int(end) if end else file_size - 1
            if end >= file_size:
                end = file_size - 1
            length = end - start + 1

            def stream_file(path, start, length):
                with open(path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    chunk_size = 8192
                    while remaining > 0:
                        read_length = min(chunk_size, remaining)
                        data = f.read(read_length)
                        if not data:
                            break
                        yield data
                        remaining -= len(data)

            response = StreamingHttpResponse(
                stream_file(output_path, start, length),
                status=206,
                content_type=content_type,
            )
            response['Content-Length'] = str(length)
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Accept-Ranges'] = 'bytes'
            response['Content-Disposition'] = f'inline; filename="clip_{pk}"'
            return response

        else:
            # Если Range не указан, отдаем весь файл
            response = StreamingHttpResponse(open(output_path, 'rb'), content_type=content_type)
            response['Content-Length'] = str(file_size)
            response['Accept-Ranges'] = 'bytes'
            response['Content-Disposition'] = f'inline; filename="clip_{pk}"'
            return response
        

class GetRenderedClipVideoAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        clip = get_object_or_404(Clip, pk=pk)
        output_path = f'{FILES_DIR}/clips/rendered_{clip.video_filename}'

        if not os.path.isfile(output_path):
            return Response({'error': 'Video file not found'}, status=404)

        file_size = os.path.getsize(output_path)
        content_type, _ = mimetypes.guess_type(output_path)
        content_type = content_type or 'application/octet-stream'

        range_header = request.headers.get('Range', '').strip()
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)

        if range_match:
            start = int(range_match.group(1))
            end = range_match.group(2)
            end = int(end) if end else file_size - 1
            if end >= file_size:
                end = file_size - 1
            length = end - start + 1

            def stream_file(path, start, length):
                with open(path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    chunk_size = 8192
                    while remaining > 0:
                        read_length = min(chunk_size, remaining)
                        data = f.read(read_length)
                        if not data:
                            break
                        yield data
                        remaining -= len(data)

            response = StreamingHttpResponse(
                stream_file(output_path, start, length),
                status=206,
                content_type=content_type,
            )
            response['Content-Length'] = str(length)
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Accept-Ranges'] = 'bytes'
            response['Content-Disposition'] = f'inline; filename="clip_{pk}"'
            return response

        else:
            # Если Range не указан, отдаем весь файл
            response = StreamingHttpResponse(open(output_path, 'rb'), content_type=content_type)
            response['Content-Length'] = str(file_size)
            response['Accept-Ranges'] = 'bytes'
            response['Content-Disposition'] = f'inline; filename="clip_{pk}"'
            return response


class DeleteClipAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        clip = get_object_or_404(Clip, pk=request.data.get('id'), user=request.user)
        overlays = TextOverlay.objects.filter(clip=clip)
        for overlay in overlays:
            overlay.delete()

        overlays = SubtitlesOverlay.objects.filter(clip=clip)
        for overlay in overlays:
            overlay.delete()
        
        overlays = ImageOverlay.objects.filter(clip=clip)
        for overlay in overlays:
            if os.path.exists(f'{FILES_DIR}/overlays/{overlay.image_filename}'):
                os.remove(f'{FILES_DIR}/overlays/{overlay.image_filename}')
            overlay.delete()


        if os.path.exists(f'{FILES_DIR}/clips/{clip.video_filename}'):
            os.remove(f'{FILES_DIR}/clips/{clip.video_filename}')
        if os.path.exists(f'{FILES_DIR}/clips/{clip.rendered_video_filename}'):
            os.remove(f'{FILES_DIR}/clips/{clip.rendered_video_filename}')
        clip.delete()

        return Response({'detail': 'Clip deleted'}, status=200)



class PreRenderClipAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        clip = get_object_or_404(Clip, id=request.data.get('id'), user=request.user)
        serializer = PreRenderClipSerializer(instance=clip, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        changed = any(getattr(clip, field) != value for field, value in serializer.validated_data.items())

        if changed or clip.status == 'error':
            serializer.save()
            clip.status = 'queued'
            clip.save()

            pre_render_clip.apply_async(args=[clip.id], priority=0)
            
            return Response({'detail': 'Clip start prerender', "id": clip.id, "status": clip.status}, status=201)

        return Response({'error': 'Nothing changes'}, status=400)
    

class RenderClipAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        clip = get_object_or_404(Clip, id=request.data.get('id'), user=request.user)

        clip.status = 'queued'
        clip.save()
        
        render_clip.apply_async(args=[clip.id], priority=1)
        return Response({'detail': 'Clip start render', "id": clip.id, "status": clip.status}, status=201)

