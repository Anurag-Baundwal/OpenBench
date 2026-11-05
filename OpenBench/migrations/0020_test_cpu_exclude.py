# Adds Test.cpu_exclude, a regular expression on the CPU name of the Machines
# that may not play a Workload. Existing Workloads get an empty one.

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0019_test_arch_filter'),
    ]

    operations = [
        migrations.AddField(
            model_name='test',
            name='cpu_exclude',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
    ]
