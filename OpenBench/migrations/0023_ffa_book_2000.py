# Adds ffa_human2000_ply8.txt (the 4PC FFA engine's books/human2000_ply8.txt): 31750 positions after
# 8 quiet plies of standard chess.com FFA games whose players average 2000+, made by its
# tools/make_book.py. ffa_human_ply8.txt stays enabled for the tests that use it.

from django.db import migrations

def create_book(apps, schema_editor):

    Book = apps.get_model('OpenBench', 'Book')

    Book.objects.update_or_create(
        name='ffa_human2000_ply8.txt', defaults={
            'source'  : '/api/books/ffa_human2000_ply8.txt/',
            'sha'     : '94fb09ab473df706e81b9b95a68812c3d544f718e81c90f781065950457fc43e',
            'enabled' : True,
        })

class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0022_ffa_book'),
    ]

    operations = [
        migrations.RunPython(create_book, migrations.RunPython.noop),
    ]
