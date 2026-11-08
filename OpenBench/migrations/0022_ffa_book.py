# Adds ffa_human_ply8.txt: FEN4 positions after 8 plies of standard chess.com FFA games, all four
# players alive (the 4PC FFA engine's books/human_ply8.txt). The Teams books stay as they are.

from django.db import migrations

def create_ffa_book(apps, schema_editor):

    Book = apps.get_model('OpenBench', 'Book')

    Book.objects.update_or_create(
        name='ffa_human_ply8.txt', defaults={
            'source'  : '/api/books/ffa_human_ply8.txt/',
            'sha'     : 'a2cb7722577b0d72072c4a79c9a99abdc616b578e8a91f184b84881a57e4132a',
            'enabled' : True,
        })


class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0021_ffa'),
    ]

    operations = [
        migrations.RunPython(create_ffa_book, migrations.RunPython.noop),
    ]
