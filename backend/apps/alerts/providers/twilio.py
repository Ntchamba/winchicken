import logging

from django.conf import settings

from apps.alerts.providers.base import SmsProvider

logger = logging.getLogger('winchicken.sms')


class TwilioSmsProvider(SmsProvider):
    """Live SMS via Twilio's REST API. Selected by SMS_PROVIDER=twilio; credentials come from
    TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_PHONE_NUMBER (env only, never hardcoded).

    `send` maps a Twilio failure onto the same `{'success': False, 'error': ...}` shape the
    console provider uses, so `apps.alerts.tasks.send_sms_task`'s existing retry/backoff logic
    handles a transient gateway error without any Twilio-specific code in the task.
    """

    def __init__(self):
        from twilio.rest import Client

        missing = [
            name for name in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER')
            if not getattr(settings, name, '')
        ]
        if missing:
            raise RuntimeError(f'SMS_PROVIDER=twilio but missing setting(s): {", ".join(missing)}')
        self._from = settings.TWILIO_PHONE_NUMBER
        self._client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    def send(self, recipient: str, body: str) -> dict:
        template = getattr(settings, 'TWILIO_TRIAL_TEMPLATE', '')
        outgoing = template or body
        if template:
            logger.info('Twilio TRIAL shim: sending template %r instead of real body %r', template, body)
        try:
            message = self._client.messages.create(to=recipient, from_=self._from, body=outgoing)
        except Exception as exc:  # twilio.base.exceptions.TwilioRestException and transport errors
            logger.warning('Twilio send to %s failed: %s', recipient, exc)
            return {'success': False, 'provider_message_id': None, 'error': str(exc)}
        logger.info('Twilio SMS -> %s (sid=%s, status=%s)', recipient, message.sid, message.status)
        return {'success': True, 'provider_message_id': message.sid, 'error': None}
