# Four-player teams engines are tested from 4PC FENs, which this fork serves
# out of Books/ itself, via /api/books/<name>/. The standard chess books seeded
# by 0015 cannot be played by a 4PC engine, so they are disabled, but kept, in
# case any existing Workload still refers to one of them by name.

from django.db import migrations

FOURPC_BOOKS = [
    ( 'fens.txt', '1a72593f8bf93f6ccf349ddf20472d29775b4c4cceb0a9f08084ef5f7e9446c8' ),
]

def create_4pc_books(apps, schema_editor):

    Book = apps.get_model('OpenBench', 'Book')

    for name, sha in FOURPC_BOOKS:
        Book.objects.update_or_create(
            name=name, defaults={ 'source' : '/api/books/%s/' % (name), 'sha' : sha, 'enabled' : True })

    Book.objects.exclude(name__in=[name for name, sha in FOURPC_BOOKS]).update(enabled=False)

class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0016_engineconfig_serverstate'),
    ]

    operations = [
        migrations.RunPython(create_4pc_books, migrations.RunPython.noop),
    ]
