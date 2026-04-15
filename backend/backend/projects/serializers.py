# serializers.py
from rest_framework import serializers
from .models import Project
from django.conf import settings
import re
import os

FILES_DIR = getattr(settings, 'MEDIA_ROOT', 'files')

YOUTUBE_REGEX = re.compile(
    r'(https?://)?(www\.)?(youtube\.com|youtu\.?be)/.+'
)

class CreateProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['name', 'video_url', 'video_filename']

    def validate(self, data):
        url = data.get('video_url')
        filename = data.get('video_filename')

        if not url and not filename:
            raise serializers.ValidationError("Either video_url or video_filename must be provided.")
        if url and filename:
            raise serializers.ValidationError("Only one of video_url or video_filename should be provided.")
        if url and not YOUTUBE_REGEX.match(url):
            raise serializers.ValidationError("Only YouTube URLs are supported.")
        if filename and not os.path.isfile(f'{FILES_DIR}/sources/{filename}'):
            raise serializers.ValidationError("Video file does not exist on server.")
        
        if filename:
            existing_project = Project.objects.filter(
                video_filename=filename
            ).exclude(status='error').first()

            if existing_project:
                raise serializers.ValidationError(
                    f"A project with filename '{filename}' already exists with status '{existing_project.status}'."
                )
            
        return data
    
    def create(self, validated_data):
        user = self.context['request'].user
        return Project.objects.create(user=user, **validated_data)


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        # fields = '__all__'
        exclude = ['interesting_filename', 'subtitles_filename', 'tracking_filename', 'created_at', 'updated_at']
