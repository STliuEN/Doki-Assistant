from django.db import migrations, models


def align_active_flag(apps, schema_editor):
    user_model = apps.get_model("user", "User")
    user_model.objects.filter(status=1, is_active=False).update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [("user", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="token_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.RunPython(align_active_flag, migrations.RunPython.noop),
    ]
