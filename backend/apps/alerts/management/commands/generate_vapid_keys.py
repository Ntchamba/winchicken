"""Generate a VAPID keypair for Web Push. Run once, paste the output into backend/.env:

    docker compose exec web python manage.py generate_vapid_keys
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


class Command(BaseCommand):
    help = 'Generate a VAPID (Web Push) public/private keypair.'

    def handle(self, *args, **options):
        key = ec.generate_private_key(ec.SECP256R1())

        private_raw = key.private_numbers().private_value.to_bytes(32, 'big')
        public_point = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
        )

        self.stdout.write('')
        self.stdout.write('Add these to backend/.env (do not commit them):')
        self.stdout.write('')
        self.stdout.write(f'VAPID_PUBLIC_KEY={_b64(public_point)}')
        self.stdout.write(f'VAPID_PRIVATE_KEY={_b64(private_raw)}')
        self.stdout.write('VAPID_SUBJECT=mailto:you@example.com')
        self.stdout.write('')
