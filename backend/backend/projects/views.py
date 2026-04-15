from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.http import StreamingHttpResponse, FileResponse
from django.shortcuts import get_object_or_404

from .serializers import (
    CreateProjectSerializer, ProjectSerializer
)
from projects.models import Project
from clips.models import Clip
from overlays.models import TextOverlay, ImageOverlay, SubtitlesOverlay
from projects.tasks import process_project

import uuid
import os
import mimetypes
import re

FILES_DIR = getattr(settings, 'MEDIA_ROOT', 'files')


class CreateProjectAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateProjectSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            project = serializer.save()

            process_project.apply_async(args=[project.id], priority=2)
            return Response({'detail': 'Project created', "id": project.id, "status": project.status}, status=201)
        return Response(serializer.errors, status=400)


class FileUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'No file provided.'}, status=400)

        ext = uploaded_file.name.split('.')[-1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            return Response({'error': 'Unsupported file format.'}, status=400)

        new_filename = f"{uuid.uuid4()}.{ext}"
        fs = FileSystemStorage(location=f'{FILES_DIR}/sources/')
        filename = fs.save(new_filename, uploaded_file)
        return Response({'detail': 'Video uploaded', 'filename': filename}, status=201)


class GetProjectsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        projects = Project.objects.filter(user=request.user)
        serializer = ProjectSerializer(projects, many=True)
        return Response({'detail': serializer.data}, status=200)


class GetProjectAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk, user=request.user)
        serializer = ProjectSerializer(project)
        return Response({'detail': serializer.data}, status=200)


class GetProjectVideoAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        # project = get_object_or_404(Project, pk=pk, user=request.user)
        project = get_object_or_404(Project, pk=pk)
        output_path = f'{FILES_DIR}/sources/{project.video_filename}'

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
            response['Content-Disposition'] = f'inline; filename="project_{pk}"'
            return response

        else:
            # Если Range не указан — отдаём весь файл
            response = StreamingHttpResponse(open(output_path, 'rb'), content_type=content_type)
            response['Content-Length'] = str(file_size)
            response['Accept-Ranges'] = 'bytes'
            response['Content-Disposition'] = f'inline; filename="project_{pk}"'
            return response


class DeleteProjectAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        project = get_object_or_404(Project, pk=request.data.get('id'), user=request.user)

        clips = Clip.objects.filter(project=project)
        for clip in clips:
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


        same_project = Project.objects.filter(video_filename=project.video_filename).exclude(id=project.id).first()
        if same_project is None:
            if os.path.exists(f'{FILES_DIR}/sources/{project.tracking_filename}'):
                os.remove(f'{FILES_DIR}/sources/{project.tracking_filename}')

            if os.path.exists(f'{FILES_DIR}/sources/{project.video_filename}'):
                os.remove(f'{FILES_DIR}/sources/{project.video_filename}')

            if os.path.exists(f'{FILES_DIR}/sources/{project.subtitles_filename}'):
                os.remove(f'{FILES_DIR}/sources/{project.subtitles_filename}')

            if os.path.exists(f'{FILES_DIR}/sources/{project.interesting_filename}'):
                 os.remove(f'{FILES_DIR}/sources/{project.interesting_filename}')

        project.delete()
        return Response({'detail': 'Project deleted'}, status=200)