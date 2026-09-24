from django.test import SimpleTestCase

from apps.core.formatting import fr_number


class FrNumberTests(SimpleTestCase):
    def test_decimal_comma_and_no_trailing_zeros(self):
        self.assertEqual(fr_number(9.5), '9,5')
        self.assertEqual(fr_number(1.59), '1,59')
        self.assertEqual(fr_number(10.0), '10')
        self.assertEqual(fr_number(10), '10')

    def test_zero_and_negative(self):
        self.assertEqual(fr_number(0), '0')
        self.assertEqual(fr_number(-2.5), '-2,5')

    def test_rounds_to_max_decimals(self):
        self.assertEqual(fr_number(1.005, 2), '1')     # float 1.005 is 1.00499...
        self.assertEqual(fr_number(1.236), '1,24')
        self.assertEqual(fr_number(2.0, 0), '2')
        self.assertEqual(fr_number(1500.0, 0), '1 500')

    def test_thousands_are_space_grouped(self):
        self.assertEqual(fr_number(1234.5), '1 234,5')
        self.assertEqual(fr_number(1000000), '1 000 000')
