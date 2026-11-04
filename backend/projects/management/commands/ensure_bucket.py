import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the configured storage bucket if it does not exist"

    def handle(self, *args, **options) -> None:
        # Create the bucket through boto3 so any S3 compatible server works
        storage = settings.STORAGES["default"]["OPTIONS"]
        bucket = storage["bucket_name"]
        client = boto3.client(
            "s3",
            endpoint_url=storage.get("endpoint_url"),
            aws_access_key_id=storage.get("access_key"),
            aws_secret_access_key=storage.get("secret_key"),
            region_name=storage.get("region_name"),
            config=Config(
                signature_version=storage.get("signature_version", "s3v4"),
                s3={"addressing_style": storage.get("addressing_style", "path")},
            ),
        )
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status != 404:
                raise CommandError(f"Cannot reach bucket {bucket}: HTTP {status}") from error
            client.create_bucket(Bucket=bucket)
            self.stdout.write(f"Created bucket {bucket}")
            return
        self.stdout.write(f"Bucket {bucket} already exists")
