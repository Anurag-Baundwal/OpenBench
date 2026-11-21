# EngineConfig.variant and Test.variant, for engines of 2-player variants whose tests are played by
# fastchess (see "variants" in Config/config.json). Existing engines and tests get '', which keeps
# them on match.py and ffa_match.py.

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0024_ffa_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='engineconfig',
            name='variant',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='test',
            name='variant',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
    ]
