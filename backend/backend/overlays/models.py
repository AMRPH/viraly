from django.db import models
from django.contrib.auth import get_user_model
from clips.models import Clip
User = get_user_model()


class TextOverlay(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='text_overlays')
    clip = models.ForeignKey(Clip, on_delete=models.CASCADE, related_name='text_overlays')

    text = models.TextField()
    font_size = models.PositiveIntegerField(default=60)
    font_color = models.CharField(max_length=7, default='#FFFFFF')

    x1 = models.FloatField()
    y1 = models.FloatField()
    x2 = models.FloatField()
    y2 = models.FloatField()
    
    start = models.FloatField()
    end = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Text [{self.id}] for Clip {self.clip.id}'



class ImageOverlay(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='image_overlays')
    clip = models.ForeignKey(Clip, on_delete=models.CASCADE, related_name='image_overlays')

    image_filename = models.TextField()

    x1 = models.FloatField()
    y1 = models.FloatField()
    x2 = models.FloatField()
    y2 = models.FloatField()
    
    start = models.FloatField()
    end = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Image [{self.id}] for Clip {self.clip.id}'
    


class SubtitlesOverlay(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subtitles_overlays')
    clip = models.ForeignKey(Clip, on_delete=models.CASCADE, related_name='subtitles_overlays')

    font_size = models.PositiveIntegerField(default=60)
    font_color = models.CharField(max_length=7, default='#FFFFFF')

    x1 = models.FloatField()
    y1 = models.FloatField()
    x2 = models.FloatField()
    y2 = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['clip'], name='unique_subtitles_overlay_per_clip')
        ]

    def __str__(self):
        return f'Subtitles [{self.id}] for Clip {self.clip.id}'