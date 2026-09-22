from django.conf import settings

from apps.alerts.providers.console import ConsoleSmsProvider


def get_sms_provider():
    """Provider selection driven by SMS_PROVIDER env var — never hardcoded credentials."""
    if settings.SMS_PROVIDER == 'console':
        return ConsoleSmsProvider()
    if settings.SMS_PROVIDER == 'twilio':
        from apps.alerts.providers.twilio import TwilioSmsProvider
        return TwilioSmsProvider()
    raise NotImplementedError(f'Unknown SMS_PROVIDER: {settings.SMS_PROVIDER}')
