"""Real SMS gateway integration (Twilio's REST API), used when SMS_PROVIDER=twilio.

Implemented against Twilio's plain HTTP REST API (no twilio-python SDK dependency) —
POST https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json, HTTP Basic Auth
with (account SID, auth token). Never called synchronously from a view — always
queued through apps.alerts.tasks.send_sms_task.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from apps.alerts.providers.base import SmsProvider

TWILIO_API_BASE = 'https://api.twilio.com/2010-04-01'


class TwilioSmsProvider(SmsProvider):
    def __init__(self):
        self.account_sid = settings.SMS_PROVIDER_ACCOUNT_SID
        self.auth_token = settings.SMS_PROVIDER_API_KEY
        self.from_number = settings.SMS_PROVIDER_SENDER_ID
        if not self.account_sid or not self.auth_token or not self.from_number:
            raise RuntimeError(
                'SMS_PROVIDER=twilio requires SMS_PROVIDER_ACCOUNT_SID, '
                'SMS_PROVIDER_API_KEY (the auth token) and SMS_PROVIDER_SENDER_ID '
                '(a Twilio-verified from-number) to be set.'
            )

    def send(self, recipient: str, body: str) -> dict:
        url = f'{TWILIO_API_BASE}/Accounts/{self.account_sid}/Messages.json'
        status_callback = getattr(settings, 'SMS_STATUS_CALLBACK_URL', '') or ''
        payload = {
            'To': recipient,
            'From': self.from_number,
            'Body': body,
        }
        if status_callback:
            payload['StatusCallback'] = status_callback

        data = urllib.parse.urlencode(payload).encode('utf-8')
        request = urllib.request.Request(url, data=data, method='POST')
        credentials = f'{self.account_sid}:{self.auth_token}'.encode('utf-8')
        import base64
        request.add_header('Authorization', b'Basic ' + base64.b64encode(credentials))
        request.add_header('Content-Type', 'application/x-www-form-urlencoded')

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                return {
                    'success': True,
                    'provider_message_id': result.get('sid'),
                    'error': None,
                }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            return {'success': False, 'provider_message_id': None, 'error': f'{exc.code}: {detail}'}
        except urllib.error.URLError as exc:
            return {'success': False, 'provider_message_id': None, 'error': str(exc.reason)}
