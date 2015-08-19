from ureport.tests import DashTest, MockTembaClient
from mock import patch
from .models import Contact


class ContactTest(DashTest):
    def setUp(self):
        super(ContactTest, self).setUp()
        self.nigeria = self.create_org('nigeria', self.admin)
        self.nigeria.set_config('state_label', "State")
        self.nigeria.set_config('district_label', "LGA")
        self.nigeria.set_config('gender_label', 'Gender')
        self.nigeria.set_config('female_label', "Female")
        self.nigeria.set_config('born_label', 'Born')

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
    def test_contact(self):
        Contact.import_contacts(self.nigeria)
        contact = Contact.objects.get()
        self.assertEqual(contact.uuid, '000-001')
        self.assertEqual(contact.org, self.nigeria)
        self.assertEqual(contact.state, 'Lagos')
        self.assertEqual(contact.district, 'Oyo')
        self.assertEqual(contact.gender, 'F')
        self.assertEqual(contact.born, 1990)




