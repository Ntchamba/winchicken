class SmsProvider:
    """Base interface for SMS gateway integrations. Never called synchronously from a view."""

    def send(self, recipient: str, body: str) -> dict:
        """Returns {'success': bool, 'provider_message_id': str | None, 'error': str | None}."""
        raise NotImplementedError
