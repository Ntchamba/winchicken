import logging

from apps.alerts.providers.base import SmsProvider

logger = logging.getLogger('winchicken.sms')


class ConsoleSmsProvider(SmsProvider):
    """Local-dev provider: logs instead of calling a real SMS gateway."""

    def send(self, recipient: str, body: str) -> dict:
        logger.info('SMS -> %s: %s', recipient, body)
        return {'success': True, 'provider_message_id': 'console-local', 'error': None}
