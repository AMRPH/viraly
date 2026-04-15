from django.db import models
from django.contrib.auth import get_user_model
from projects.models import Project
User = get_user_model()


class Clip(models.Model):
    STATUS_CHOICES = [
        ('queued', 'В очереди'),
        ('processing', 'Обрабатывается'),
        ('done', 'Готово'),
        ('error', 'Ошибка'),
    ]

    FORMAT_CHOICES = [
        ('9:16', 'Vertical (9:16)'),
        ('1:1', 'Square (1:1)'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clips')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='clips')
    video_filename = models.TextField(blank=True, null=True)
    rendered_video_filename = models.TextField(blank=True, null=True)
    
    start = models.FloatField()
    end = models.FloatField()
    crop = models.CharField(
        max_length=10,
        choices=FORMAT_CHOICES,
        default='9:16'
    )

    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued', db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Clip {self.id} ({self.start:.2f}s – {self.end:.2f}s)"