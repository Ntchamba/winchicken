"""A duplicate employee email is refused with the app's own French sentence.

Campaign 3, in the browser: "Un objet user avec ce champ email existe déjà." — Django's generic
unique message — because the model's UniqueValidator ran before `validate_email`, whose
"Un compte utilise déjà cet email." was never reached (and it is the case-insensitive check).
"""
from rest_framework.test import APITestCase

from apps.core.models import Farm, User, UserRole, create_role_profile


class EmployeeEmailTests(APITestCase):
    def setUp(self):
        farm = Farm.objects.create(name='Ferme Emails')
        admin = User.objects.create_user(email='admin@emails.local', password='x', name='A', role=UserRole.ADMIN, farm=farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        self.body = {'name': 'Joseph', 'civility': 'M', 'role': 'FARMER', 'password': 'Campagne3-Fermier!'}

    def test_an_email_already_used_gets_the_french_sentence(self):
        response = self.client.post('/api/employees/', {**self.body, 'email': 'admin@emails.local'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['email'], ['Un compte utilise déjà cet email.'])

    def test_case_does_not_make_it_a_different_email(self):
        response = self.client.post('/api/employees/', {**self.body, 'email': 'ADMIN@Emails.local'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['email'], ['Un compte utilise déjà cet email.'])
