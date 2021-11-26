from datetime import timedelta

from django.utils import timezone

from dash.categories.models import Category
from ureport.flows.models import FlowResult, FlowResultCategory
from ureport.locations.models import Boundary
from ureport.stats.models import AgeSegment, ContactEngagementActivity, GenderSegment, PollContactResult, SchemeSegment
from ureport.tests import UreportTest


class PollResultsTest(UreportTest):
    def setUp(self):
        super(PollResultsTest, self).setUp()

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

        self.poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        self.flow_result, created = FlowResult.objects.get_or_create(
            org=self.poll.org, flow_uuid=self.poll.flow_uuid, result_uuid="step-uuid", result_name="question 1"
        )

        self.flow_result_category_no, created = FlowResultCategory.objects.get_or_create(
            flow_result_id=self.flow_result.id, category="No", is_active=True
        )

        self.flow_result_category_yes, created = FlowResultCategory.objects.get_or_create(
            flow_result_id=self.flow_result.id, category="Yes", is_active=True
        )

        # boundaries fetched
        self.country = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-NIGERIA",
            name="Nigeria",
            backend=self.rapidpro_backend,
            level=Boundary.COUNTRY_LEVEL,
            parent=None,
            geometry='{"foo":"bar-country"}',
        )
        self.state = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-LAGOS",
            name="Lagos",
            backend=self.rapidpro_backend,
            level=Boundary.STATE_LEVEL,
            parent=self.country,
            geometry='{"foo":"bar-state"}',
        )
        self.district = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-OYO",
            name="Oyo",
            backend=self.rapidpro_backend,
            level=Boundary.DISTRICT_LEVEL,
            parent=self.state,
            geometry='{"foo":"bar-state"}',
        )
        self.ward = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-IKEJA",
            name="Ikeja",
            backend=self.rapidpro_backend,
            level=Boundary.WARD_LEVEL,
            parent=self.district,
            geometry='{"foo":"bar-state"}',
        )

        self.female_gender = GenderSegment.objects.get(gender="F")
        self.male_gender = GenderSegment.objects.get(gender="M")

        self.age1 = AgeSegment.objects.all().order_by("min_age").first()

        self.tel_scheme = SchemeSegment.objects.create(scheme="tel")

        self.now = timezone.now()
        self.last_week = self.now - timedelta(days=7)
        self.last_month = self.now - timedelta(days=30)

    def test_contact_engagement_activity(self):
        self.assertFalse(ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))

        PollContactResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            flow_result=self.flow_result,
            date=self.now,
            contact="contact-uuid",
        )

        self.assertFalse(ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))

        PollContactResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            flow_result=self.flow_result,
            flow_result_category=self.flow_result_category_no,
            date=self.now,
            contact="contact-uuid",
        )

        self.assertTrue(ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))
        self.assertEqual(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").count(), 12
        )
        self.assertFalse(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(
                age_segment=None
            )
        )
        self.assertFalse(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(
                gender_segment=None
            )
        )
        self.assertFalse(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(location=None)
        )
        self.assertFalse(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(
                scheme_segment=None
            )
        )

        PollContactResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            flow_result=self.flow_result,
            flow_result_category=self.flow_result_category_no,
            contact="contact-uuid",
            text="Nah",
            date=self.now,
            location=self.ward,
            scheme_segment=self.tel_scheme,
        )

        self.assertTrue(ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))
        self.assertEqual(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").count(), 12
        )
        self.assertFalse(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(
                age_segment=None
            )
        )
        self.assertFalse(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(
                gender_segment=None
            )
        )
        self.assertTrue(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(location=None)
        )
        self.assertTrue(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(
                scheme_segment=None
            )
        )

        PollContactResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            flow_result=self.flow_result,
            flow_result_category=self.flow_result_category_yes,
            contact="contact-uuid2",
            text="Yeah",
            age_segment=self.age1,
            gender_segment=self.male_gender,
            date=self.now,
            location=self.ward,
            scheme_segment=self.tel_scheme,
        )

        self.assertTrue(ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid2"))
        self.assertEqual(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid2").count(), 12
        )
        self.assertTrue(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid2").exclude(
                age_segment=None
            )
        )
        self.assertTrue(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid2").exclude(
                gender_segment=None
            )
        )
        self.assertTrue(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid2").exclude(location=None)
        )
        self.assertTrue(
            ContactEngagementActivity.objects.filter(org=self.nigeria, contact="contact-uuid2").exclude(
                scheme_segment=None
            )
        )
