# Adds Test.arch_filter, a regular expression on the ISA of the Machines that
# may play a Workload, as in Fishtest. Existing Workloads get an empty filter.

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0018_fens_100k_book'),
    ]

    operations = [
        migrations.AddField(
            model_name='test',
            name='arch_filter',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
    ]
