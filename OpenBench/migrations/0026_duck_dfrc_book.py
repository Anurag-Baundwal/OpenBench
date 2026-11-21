# Adds Duck_DFRC.epd, the book of wakwak's duck chess tests on chess.n9x.co: 5,030,384 double Fischer
# random openings about ten plies in, with no duck on the board yet (333 MB, 121 MB zipped). The sha
# is that of the extracted DFRC_4852_v2.epd, which Workers check after unzipping.

from django.db import migrations

def create_duck_dfrc(apps, schema_editor):

    Book = apps.get_model('OpenBench', 'Book')

    Book.objects.update_or_create(
        name='Duck_DFRC.epd', defaults={
            'source'  : 'https://file.ax/DFRC_4852_v2.epd.zip',
            'sha'     : '54f494a294c83aeb6ef5734a8c6064130ed0588d94a57c4abf31d76b756c9c6e',
            'enabled' : True,
        })

class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0025_variant'),
    ]

    operations = [
        migrations.RunPython(create_duck_dfrc, migrations.RunPython.noop),
    ]
