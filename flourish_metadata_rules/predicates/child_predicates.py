from dateutil.relativedelta import relativedelta
from django.apps import apps as django_apps
from edc_base.utils import age, get_utcnow
from edc_constants.constants import FEMALE, YES, POS, NEG
from edc_metadata_rules import PredicateCollection
from edc_reference.models import Reference

from flourish_caregiver.helper_classes import MaternalStatusHelper


class UrlMixinNoReverseMatch(Exception):
    pass


class ChildPredicates(PredicateCollection):
    app_label = 'flourish_child'
    pre_app_label = 'pre_flourish'
    maternal_app_label = 'flourish_caregiver'
    visit_model = f'{app_label}.childvisit'
    maternal_visit_model = 'flourish_caregiver.maternalvisit'

    @property
    def maternal_visit_model_cls(self):
        return django_apps.get_model(self.maternal_visit_model)

    def func_hiv_exposed(self, visit=None, **kwargs):
        """
        Get the pregnancy status of the mother, is positive it means
        the child was exposed to HIV
        """
        child_subject_identifier = visit.subject_identifier
        caregiver_subject_identifier = child_subject_identifier[0:16]
        maternal_status_helper = MaternalStatusHelper(
            subject_identifier=caregiver_subject_identifier)
        return maternal_status_helper.hiv_status == POS

    def get_latest_maternal_hiv_status(self, visit=None):
        maternal_subject_id = visit.subject_identifier[:-3]
        maternal_visit = self.maternal_visit_model_cls.objects.filter(
            subject_identifier=maternal_subject_id)

        if maternal_visit:
            latest_visit = maternal_visit.latest('report_datetime')
            maternal_status_helper = MaternalStatusHelper(
                maternal_visit=latest_visit)
        else:
            maternal_status_helper = MaternalStatusHelper(
                subject_identifier=maternal_subject_id)
        return maternal_status_helper

    def mother_pregnant(self, visit=None, **kwargs):
        """Returns true if expecting
        """
        enrollment_model = django_apps.get_model(
            f'{self.maternal_app_label}.antenatalenrollment')
        try:
            enrollment_model.objects.get(subject_identifier=visit.subject_identifier[:-3])
        except enrollment_model.DoesNotExist:
            return False
        else:
            maternal_delivery_cls = django_apps.get_model(
                f'{self.maternal_app_label}.maternaldelivery')
            try:
                maternal_delivery_cls.objects.get(
                    subject_identifier=visit.subject_identifier[:-3])
            except maternal_delivery_cls.DoesNotExist:
                return True
        return False

    def get_child_age(self, visit=None, **kwargs):
        """Returns child age
        """
        if not self.mother_pregnant(visit=visit):
            caregiver_child_consent_cls = django_apps.get_model(
                f'{self.maternal_app_label}.caregiverchildconsent')
            consents = caregiver_child_consent_cls.objects.filter(
                subject_identifier=visit.subject_identifier)
            if consents:
                caregiver_child_consent = consents.latest('consent_datetime')
                return age(caregiver_child_consent.child_dob, get_utcnow())

    def child_age_at_enrolment(self, visit):

        if (not self.mother_pregnant(visit=visit)
                and not self.func_consent_study_pregnant(visit)):

            dummy_consent_cls = django_apps.get_model(
                f'{self.app_label}.childdummysubjectconsent')

            dummy_consents = dummy_consent_cls.objects.filter(
                subject_identifier=visit.subject_identifier)
            if dummy_consents:
                dummy_consent = dummy_consents.latest('consent_datetime')
                return dummy_consent.age_at_consent

    def func_consent_study_pregnant(self, visit=None, **kwargs):
        """Returns True if participant's mother consented to the study in pregnancy
        """
        maternal_delivery_cls = django_apps.get_model(
            f'{self.maternal_app_label}.maternaldelivery')
        try:
            maternal_delivery_cls.objects.get(
                subject_identifier=visit.subject_identifier[:-3],
                live_infants_to_register__gte=1)
        except maternal_delivery_cls.DoesNotExist:
            return False
        else:
            return True

    def func_mother_preg_pos(self, visit=None, **kwargs):
        """ Returns True if participant's mother consented to the study in
            pregnancy and latest hiv status is POS.
        """
        hiv_status = self.get_latest_maternal_hiv_status(
            visit=visit).hiv_status
        return (self.func_consent_study_pregnant(visit=visit) and hiv_status == POS)

    def func_specimen_storage_consent(self, visit=None, **kwargs):
        """Returns True if participant's mother consented to repository blood specimen
        storage at enrollment.
        """

        child_age = self.get_child_age(visit=visit)

        consent_cls = None
        subject_identifier = None

        if child_age < 7:
            consent_cls = django_apps.get_model(
                f'{self.maternal_app_label}.caregiverchildconsent')
            subject_identifier = visit.subject_ifdentifier[:-3]

        elif child_age >= 18:
            consent_cls = django_apps.get_model(
                f'{self.app_label}.childcontinuedconsent')
            subject_identifier = visit.subject_ifdentifier
        else:
            consent_cls = django_apps.get_model(
                f'{self.app_label}.childassent')
            subject_identifier = visit.subject_ifdentifier

        if consent_cls and subject_identifier:
            consent_objs = consent_cls.objects.filter(
                subject_identifier=subject_identifier)

            if consent_objs:
                consent_obj = consent_objs.latest('consent_datetime')
                return consent_obj.specimen_consent == YES
            return False

    def func_7_years_older(self, visit=None, **kwargs):
        """Returns true if participant is 7 years or older
        """
        child_age = self.get_child_age(visit=visit)
        return child_age.years >= 7 if child_age else False

    def func_12_years_older(self, visit=None, **kwargs):
        """Returns true if participant is 12 years or older
        """
        child_age = self.get_child_age(visit=visit)
        return child_age.years >= 12 if child_age else False

    def func_12_years_older_female(self, visit=None, **kwargs):
        """Returns true if participant is 12 years or older
        """
        assent_model = django_apps.get_model(f'{self.app_label}.childassent')

        assent_objs = assent_model.objects.filter(
            subject_identifier=visit.subject_identifier)

        if assent_objs:
            assent_obj = assent_objs.latest('consent_datetime')

            child_age = age(assent_obj.dob, get_utcnow())
            return child_age.years >= 12 and assent_obj.gender == FEMALE

    def func_2_months_older(self, visit=None, **kwargs):
        """Returns true if participant is 2 months or older
        """
        child_age = self.get_child_age(visit=visit)
        return child_age.months >= 2 if child_age else False

    def func_36_months_younger(self, visit=None, **kwargs):
        child_age = self.child_age_at_enrolment(visit=visit)

        return ((child_age.years * 12) + child_age.months) < 36 if child_age else False

    def func_continued_consent(self, visit=None, **kwargs):
        """Returns True if participant is over 18 and continued consent has been completed
        """
        continued_consent_cls = django_apps.get_model(
            f'{self.app_label}.childcontinuedconsent')

        continued_consent_objs = continued_consent_cls.objects.filter(
            subject_identifier=visit.subject_identifier)

        if continued_consent_objs:
            return True
        return False

    def func_3_months_old(self, visit=None, **kwargs):
        """
        Returns True if the participant is 3 months old
        """
        child_age = self.get_child_age(visit=visit)
        if child_age.months == 3 and child_age.years == 0:
            previous_dev_screening = Reference.objects.filter(
                model=f'{self.app_label}.infantdevscreening3months',
                identifier=visit.appointment.subject_identifier,
                report_datetime__lt=visit.report_datetime).order_by(
                '-report_datetime').first()

            return False if previous_dev_screening else True
        return False

    def func_6_months_old(self, visit=None, **kwargs):
        """
        Returns True if the participant is 6 months old
        """
        child_age = self.get_child_age(visit=visit)
        if child_age.years == 0 and child_age.months == 6:
            previous_dev_screening = Reference.objects.filter(
                model=f'{self.app_label}.infantdevscreening6months',
                identifier=visit.appointment.subject_identifier,
                report_datetime__lt=visit.report_datetime).order_by(
                '-report_datetime').first()

            return False if previous_dev_screening else True
        return False

    def func_12_months_old(self, visit=None, **kwargs):
        """
        Returns True if the participant is 12 months old
        """
        child_age = self.get_child_age(visit=visit)
        if child_age.years == 1 and child_age.months < 7:
            previous_dev_screening = Reference.objects.filter(
                model=f'{self.app_label}.infantdevscreening12months',
                identifier=visit.appointment.subject_identifier,
                report_datetime__lt=visit.report_datetime).order_by(
                '-report_datetime').first()

            return False if previous_dev_screening else True
        return False

    def func_18_months_old(self, visit=None, **kwargs):
        """
        Returns True if the participant is 18 months old
        """
        child_age = self.get_child_age(visit=visit)
        if child_age.years == 1 and child_age.months <= 6:
            previous_dev_screening = Reference.objects.filter(
                model=f'{self.app_label}.infantdevscreening18months',
                identifier=visit.appointment.subject_identifier,
                report_datetime__lt=visit.report_datetime).order_by(
                '-report_datetime').first()

            return False if previous_dev_screening else True
        return False

    def func_36_months_old(self, visit=None, **kwargs):
        """
        Returns True if the participant is 36 months old
        """
        child_age = self.get_child_age(visit=visit)
        if child_age.years == 3:
            previous_dev_screening = Reference.objects.filter(
                model=f'{self.app_label}.infantdevscreening36months',
                identifier=visit.appointment.subject_identifier,
                report_datetime__lt=visit.report_datetime).order_by(
                '-report_datetime').first()

            return False if previous_dev_screening else True
        return False

    def func_60_months_old(self, visit=None, **kwargs):
        """
        Returns True if the participant is 5 years old
        """
        child_age = self.get_child_age(visit=visit)
        if child_age.years == 5:
            previous_dev_screening = Reference.objects.filter(
                model=f'{self.app_label}.infantdevscreening60months',
                identifier=visit.appointment.subject_identifier,
                report_datetime__lt=visit.report_datetime).order_by(
                '-report_datetime').first()

            return False if previous_dev_screening else True
        return False

    def func_72_months_old(self, visit=None, **kwargs):
        """
        Returns True if the participant is 6 years old
        """
        child_age = self.get_child_age(visit=visit)
        if child_age.years == 6:
            previous_dev_screening = Reference.objects.filter(
                model=f'{self.app_label}.infantdevscreening72months',
                identifier=visit.appointment.subject_identifier,
                report_datetime__lt=visit.report_datetime).order_by(
                '-report_datetime').first()
            return False if previous_dev_screening else True
        return False

    def func_forth_eighth_quarter(self, visit=None, **kwargs):
        """
        Returns true if the visit is the 4th annual quarterly call
        """
        child_age = self.get_child_age(visit=visit)
        caregiver_child_consent_cls = django_apps.get_model(
            f'{self.maternal_app_label}.caregiverchildconsent')
        consents = caregiver_child_consent_cls.objects.filter(
            subject_identifier=visit.subject_identifier)
        if child_age.years >= 3 and consents:
            caregiver_child_consent = consents.latest('consent_datetime')
            child_is_three_at_date = caregiver_child_consent.child_dob - relativedelta(
                years=3, months=0)
            if visit.report_datetime.date() > child_is_three_at_date:
                previous_visit = Reference.objects.filter(
                    model=f'{self.app_label}.childvisit',
                    identifier=visit.appointment.subject_identifier,
                    report_datetime__lt=visit.report_datetime).order_by(
                    '-report_datetime').count()

                if previous_visit != 0 and previous_visit % 4 == 0:
                    return True
        return False

    def func_2000D_and_negative(self, visit, **kwargs):
        """

        Returns True if the mother is hiv negative and and when its visit 2000D

        """

        hiv_status = self.get_latest_maternal_hiv_status(

            visit=visit).hiv_status

        return hiv_status == NEG and visit.visit_code == '2000D'
