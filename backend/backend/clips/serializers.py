# serializers.py
from rest_framework import serializers
from .models import Clip
from django.conf import settings

MIN_DURATION = getattr(settings, 'MIN_CLIP_DURATION', 8.0)
MAX_DURATION = getattr(settings, 'MAX_CLIP_DURATION', 120.0)

class PreRenderClipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clip
        fields = [
            'id',
            'crop',
            'start',
            'end'
        ]
    

    def validate(self, data):
        start = data.get('start')
        end = data.get('end')
        if start is not None and start <= 0:
            raise serializers.ValidationError("Start must be greater than 0.")
        if start is not None and end is not None:
            if end - start < MIN_DURATION:
                raise serializers.ValidationError(f"The clip must be at least {MIN_DURATION} seconds long.")
            if end - start > MAX_DURATION:
                raise serializers.ValidationError(f"The clip duration cannot exceed {MAX_DURATION} seconds.")
            
        project = self.instance.project
        if  end is not None and project and end > project.duration:
            raise serializers.ValidationError("End cannot exceed the project duration.")
        return data


class ClipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clip
        # fields = '__all__'
        exclude = ['created_at', 'updated_at']