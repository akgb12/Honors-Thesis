import uuid

from django.db import models


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class ProjectFile(models.Model):
    project = models.ForeignKey(Project, related_name="files", on_delete=models.CASCADE)
    path = models.CharField(max_length=1024)
    size = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["path"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "path"],
                name="unique_project_file_path",
            )
        ]


class Run(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        BLOCKED = "blocked", "Blocked"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    class Effort(models.TextChoices):
        BASELINE = "baseline", "Baseline"
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, related_name="runs", on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=Status, default=Status.QUEUED)
    effort = models.CharField(max_length=16, choices=Effort)
    main_file = models.CharField(max_length=1024, blank=True)
    seed_weak = models.CharField(max_length=1024, null=True, blank=True)
    model_provider = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    run_dir = models.CharField(max_length=1024, blank=True)
    stop_reason = models.CharField(max_length=64, blank=True)
    a_score = models.FloatField(null=True, blank=True)
    f_score = models.FloatField(null=True, blank=True)
    input_tokens = models.PositiveBigIntegerField(default=0)
    output_tokens = models.PositiveBigIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
