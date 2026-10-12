import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = (
        'Create the first superuser from the DJANGO_SUPERUSER_USERNAME, '
        'DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD environment variables'
    )

    def handle(self, *args, **options):
        if User.objects.count() == 0:
            username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
            email = os.environ.get('DJANGO_SUPERUSER_EMAIL', username + '@example.com')
            password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
            if not password:
                raise CommandError('Set DJANGO_SUPERUSER_PASSWORD to initialize the admin account')
            print('Creating account for %s (%s)' % (username, email))
            User.objects.create_superuser(email=email, username=username, password=password)
        else:
            print('Admin accounts can only be initialized if no Accounts exist')
