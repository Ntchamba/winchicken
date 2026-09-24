"""The suite must never reach a real SMS gateway, push service or the stack's live worker —
the stacks' .env carries live credentials (config/settings.py, "Test isolation")."""
from django.conf import settings
from django.test import SimpleTestCase

from config.celery import app


class TestIsolationTests(SimpleTestCase):
    def test_no_real_sms_push_or_broker_under_the_test_runner(self):
        self.assertTrue(settings.RUNNING_TESTS)
        self.assertEqual(settings.SMS_PROVIDER, 'console')
        self.assertFalse(settings.WEB_PUSH_ENABLED)
        self.assertTrue(app.conf.task_always_eager)
