# Adds fens_100k.txt, 100,000 balanced 4PC openings made by
# Scripts/generate_fens.py with seed 2 and its default settings, as the book of
# new tests. fens.txt stays enabled, since Workloads refer to Books by name, and
# tests created before this one keep playing their openings from it.

from django.db import migrations

def create_fens_100k(apps, schema_editor):

    Book = apps.get_model('OpenBench', 'Book')

    Book.objects.update_or_create(
        name='fens_100k.txt', defaults={
            'source'  : '/api/books/fens_100k.txt/',
            'sha'     : 'f453685f483f5b77a767f712452429972996fe1f7b69dfa36a30d6998dbaa475',
            'enabled' : True,
        })

class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0017_4pc_books'),
    ]

    operations = [
        migrations.RunPython(create_fens_100k, migrations.RunPython.noop),
    ]
