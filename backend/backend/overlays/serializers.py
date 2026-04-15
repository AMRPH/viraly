from rest_framework import serializers
from .models import TextOverlay, ImageOverlay, SubtitlesOverlay
from clips.models import Clip
from django.conf import settings
import os

FILES_DIR = getattr(settings, 'MEDIA_ROOT', 'files')


class BaseOverlaySerializer(serializers.ModelSerializer):
    clip = serializers.PrimaryKeyRelatedField(queryset=Clip.objects.all())

    def validate_coordinates(self, data):
        errors = {}

        x1, x2 = data.get('x1'), data.get('x2')
        y1, y2 = data.get('y1'), data.get('y2')

        if x1 is None:
            errors['x1'] = "x1 is required"
        elif not (0 <= x1 <= 1080):
            errors['x1'] = "x1 must be between 0 and 1080"

        if x2 is None:
            errors['x2'] = "x2 is required"
        elif not (0 <= x2 <= 1080):
            errors['x2'] = "x2 must be between 0 and 1080"
        elif x1 is not None and x2 < x1:
            errors['x2'] = "x2 must be greater than or equal to x1"

        if y1 is None:
            errors['y1'] = "y1 is required"
        elif not (0 <= y1 <= 1920):
            errors['y1'] = "y1 must be between 0 and 1920"

        if y2 is None:
            errors['y2'] = "y2 is required"
        elif not (0 <= y2 <= 1920):
            errors['y2'] = "y2 must be between 0 and 1920"
        elif y1 is not None and y2 < y1:
            errors['y2'] = "y2 must be greater than or equal to y1"

        return errors

    def validate_timings(self, data):
        errors = {}

        start = data.get('start')
        end = data.get('end')
        clip = data.get('clip')

        if start is None:
            errors['start'] = "start is required"
        if end is None:
            errors['end'] = "end is required"
        if clip is None:
            errors['clip'] = "clip is required"

        if start is not None and end is not None:
            if end <= start:
                errors['end'] = "end must be greater than start"
            if clip is not None:
                clip_duration = clip.end - clip.start
                if end > clip_duration:
                    errors['end'] = f"end cannot be greater than clip duration ({clip_duration})"

        return errors

    def validate(self, data):
        errors = {}
        errors.update(self.validate_coordinates(data))
        errors.update(self.validate_timings(data))
        if errors:
            raise serializers.ValidationError(errors)
        return data


class CreateImageOverlaySerializer(BaseOverlaySerializer):
    class Meta:
        model = ImageOverlay
        fields = ['image_filename', 'x1', 'y1', 'x2', 'y2', 'clip', 'start', 'end']

    def validate(self, data):
        errors = {}

        image_filename = data.get('image_filename')
        if image_filename and not os.path.isfile(f'{FILES_DIR}/overlays/{image_filename}'):
            errors['image_filename'] = "Image file does not exist on server."

        try:
            super().validate(data)
        except serializers.ValidationError as e:
            errors.update(e.detail)

        if errors:
            raise serializers.ValidationError(errors)
        return data

    def create(self, validated_data):
        user = self.context['request'].user
        return ImageOverlay.objects.create(user=user, **validated_data)


class ImageOverlaySerializer(BaseOverlaySerializer):
    class Meta:
        model = ImageOverlay
        # fields = '__all__'
        read_only_fields = ['clip', 'user', 'id', 'created_at', 'image_filename']
        exclude = ['created_at']

    def validate(self, data):
        errors = {}

        image_filename = data.get('image_filename')
        if image_filename and not os.path.isfile(f'{FILES_DIR}/overlays/{image_filename}'):
            errors['image_filename'] = "Image file does not exist on server."

        try:
            super().validate(data)
        except serializers.ValidationError as e:
            errors.update(e.detail)

        if errors:
            raise serializers.ValidationError(errors)

        return data




class CreateTextOverlaySerializer(BaseOverlaySerializer):
    class Meta:
        model = TextOverlay
        fields = ['text', 'font_size', 'font_color', 'x1', 'y1', 'x2', 'y2', 'clip', 'start', 'end']

    def create(self, validated_data):
        user = self.context['request'].user
        return TextOverlay.objects.create(user=user, **validated_data)


class TextOverlaySerializer(BaseOverlaySerializer):
    class Meta:
        model = TextOverlay
        # fields = '__all__'
        read_only_fields = ['clip', 'user', 'id', 'created_at']
        exclude = ['created_at']



class CreateSubtitlesOverlaySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubtitlesOverlay
        fields = [
            'font_size', 'font_color',
            'x1', 'y1', 'x2', 'y2',
            'clip'
        ]

    def validate_clip(self, clip):
        if SubtitlesOverlay.objects.filter(clip=clip).exists():
            raise serializers.ValidationError("This clip already has a Subtitles.")
        return clip

    def validate(self, data):
        errors = {}

        # Координаты X
        x1, x2 = data.get('x1'), data.get('x2')
        if x1 is None:
            errors['x1'] = "x1 is required"
        elif not (0 <= x1 <= 1080):
            errors['x1'] = "x1 must be between 0 and 1080"

        if x2 is None:
            errors['x2'] = "x2 is required"
        elif not (0 <= x2 <= 1080):
            errors['x2'] = "x2 must be between 0 and 1080"
        elif x1 is not None and x2 < x1:
            errors['x2'] = "x2 must be greater than or equal to x1"

        # Координаты Y
        y1, y2 = data.get('y1'), data.get('y2')
        if y1 is None:
            errors['y1'] = "y1 is required"
        elif not (0 <= y1 <= 1920):
            errors['y1'] = "y1 must be between 0 and 1920"

        if y2 is None:
            errors['y2'] = "y2 is required"
        elif not (0 <= y2 <= 1920):
            errors['y2'] = "y2 must be between 0 and 1920"
        elif y1 is not None and y2 < y1:
            errors['y2'] = "y2 must be greater than or equal to y1"

        if errors:
            raise serializers.ValidationError(errors)

        return data

    def create(self, validated_data):
        user = self.context['request'].user
        return SubtitlesOverlay.objects.create(user=user, **validated_data)


class SubtitlesOverlaySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubtitlesOverlay
        read_only_fields = ['clip', 'user', 'id', 'created_at']
        exclude = ['created_at']
    

    def validate_clip(self, clip):
        if SubtitlesOverlay.objects.filter(clip=clip).exists():
            raise serializers.ValidationError("This clip already has a Subtitles.")
        return clip

    def validate(self, data):
        errors = {}

        # Координаты X
        x1, x2 = data.get('x1'), data.get('x2')
        if x1 is None:
            errors['x1'] = "x1 is required"
        elif not (0 <= x1 <= 1080):
            errors['x1'] = "x1 must be between 0 and 1080"

        if x2 is None:
            errors['x2'] = "x2 is required"
        elif not (0 <= x2 <= 1080):
            errors['x2'] = "x2 must be between 0 and 1080"
        elif x1 is not None and x2 < x1:
            errors['x2'] = "x2 must be greater than or equal to x1"

        # Координаты Y
        y1, y2 = data.get('y1'), data.get('y2')
        if y1 is None:
            errors['y1'] = "y1 is required"
        elif not (0 <= y1 <= 1920):
            errors['y1'] = "y1 must be between 0 and 1920"

        if y2 is None:
            errors['y2'] = "y2 is required"
        elif not (0 <= y2 <= 1920):
            errors['y2'] = "y2 must be between 0 and 1920"
        elif y1 is not None and y2 < y1:
            errors['y2'] = "y2 must be greater than or equal to y1"

        if errors:
            raise serializers.ValidationError(errors)

        return data