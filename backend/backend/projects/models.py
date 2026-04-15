from django.db import models
from django.contrib.auth import get_user_model
User = get_user_model()

class Project(models.Model):
    STATUS_CHOICES = [
        ('queued', 'В очереди'),
        ('processing', 'Обрабатывается'),
        ('done', 'Готово'),
        ('error', 'Ошибка'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255)
    video_url = models.URLField(blank=True, null=True)
    video_filename = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued', db_index=True)
    duration = models.FloatField(null=True)

    interesting_filename = models.TextField(blank=True, null=True)
    tracking_filename = models.TextField(blank=True, null=True)
    subtitles_filename = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Project {self.id} — {self.name}"