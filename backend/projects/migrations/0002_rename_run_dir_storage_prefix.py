from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="run",
            old_name="run_dir",
            new_name="storage_prefix",
        ),
    ]
