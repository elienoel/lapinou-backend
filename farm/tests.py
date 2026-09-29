import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from .models import Cage, Litter, Mating, Rabbit


class MatingEditAndLitterFromMatingTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='eleveur', password='x')
        self.other = User.objects.create_user(username='autre', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        born = date.today() - timedelta(days=400)
        self.male = Rabbit.objects.create(owner=self.user, name='Flash', tag_number='M1', gender='M', birth_date=born)
        self.male2 = Rabbit.objects.create(owner=self.user, name='Titan', tag_number='M2', gender='M', birth_date=born)
        self.female = Rabbit.objects.create(owner=self.user, name='Bella', tag_number='F1', gender='F', birth_date=born)
        self.female2 = Rabbit.objects.create(owner=self.user, name='Luna', tag_number='F2', gender='F', birth_date=born)

    def _create_mating(self, **extra):
        payload = {'male': self.male.id, 'female': self.female.id, 'mating_date': '2026-01-01'}
        payload.update(extra)
        res = self.client.post('/api/farm/matings/', payload, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.data['data']

    def test_patch_mating_recalculates_dates_and_swaps_female(self):
        mating = self._create_mating()
        self.female.refresh_from_db()
        self.assertEqual(self.female.status, Rabbit.Status.PREGNANT)

        res = self.client.patch(
            f"/api/farm/matings/{mating['id']}/",
            {'mating_date': '2026-02-01', 'female': self.female2.id, 'male': self.male2.id, 'notes': 'corrigé'},
            format='json',
        )
        self.assertEqual(res.status_code, 200, res.content)
        data = res.data['data']
        self.assertEqual(data['palpation_date'], '2026-02-13')
        self.assertEqual(data['nest_box_date'], '2026-03-01')
        self.assertEqual(data['expected_kindling_date'], '2026-03-04')
        self.assertEqual(data['male'], self.male2.id)
        self.assertEqual(data['notes'], 'corrigé')

        self.female.refresh_from_db()
        self.female2.refresh_from_db()
        self.assertEqual(self.female.status, Rabbit.Status.ACTIVE)
        self.assertEqual(self.female2.status, Rabbit.Status.PREGNANT)

    def test_patch_status_failed_releases_female(self):
        mating = self._create_mating()
        res = self.client.patch(f"/api/farm/matings/{mating['id']}/", {'status': 'failed'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.female.refresh_from_db()
        self.assertEqual(self.female.status, Rabbit.Status.ACTIVE)

    def test_cannot_use_foreign_rabbit(self):
        stranger = Rabbit.objects.create(
            owner=self.other, name='X', tag_number='X1', gender='F', birth_date=date.today() - timedelta(days=300)
        )
        mating = self._create_mating()
        res = self.client.patch(f"/api/farm/matings/{mating['id']}/", {'female': stranger.id}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_litter_from_mating_derives_parents(self):
        mating = self._create_mating()
        res = self.client.post(
            '/api/farm/litters/',
            {'mating': mating['id'], 'birth_date': '2026-02-01', 'born_alive': 7, 'still_born': 1},
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.content)
        litter = Litter.objects.get(pk=res.data['data']['id'])
        self.assertEqual(litter.mother_id, self.female.id)
        self.assertEqual(litter.father_id, self.male.id)
        self.assertEqual(Mating.objects.get(pk=mating['id']).status, Mating.Status.KINDLED)
        self.female.refresh_from_db()
        self.assertEqual(self.female.status, Rabbit.Status.LACTATING)

    def test_litter_requires_mating(self):
        res = self.client.post(
            '/api/farm/litters/', {'birth_date': '2026-02-01', 'born_alive': 5}, format='json'
        )
        self.assertEqual(res.status_code, 400)

    def test_second_litter_for_same_mating_rejected(self):
        mating = self._create_mating()
        body = {'mating': mating['id'], 'birth_date': '2026-02-01', 'born_alive': 5}
        self.assertEqual(self.client.post('/api/farm/litters/', body, format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/farm/litters/', body, format='json').status_code, 400)


class CageTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='eleveur2', password='x')
        self.other = User.objects.create_user(username='autre2', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        born = date.today() - timedelta(days=400)
        self.r1 = Rabbit.objects.create(owner=self.user, name='Flash', tag_number='M1', gender='M', birth_date=born)
        self.r2 = Rabbit.objects.create(owner=self.user, name='Bella', tag_number='F1', gender='F', birth_date=born)

    def _create_cage(self, **extra):
        payload = {'name': 'A1', 'rows_count': 3}
        payload.update(extra)
        return self.client.post('/api/farm/cages/', payload, format='json')

    def test_create_cage_exposes_empty_compartments(self):
        res = self._create_cage()
        self.assertEqual(res.status_code, 201, res.content)
        data = res.data['data']
        self.assertEqual(data['compartments_count'], 3)
        self.assertEqual([c['number'] for c in data['compartments']], [1, 2, 3])
        self.assertTrue(all(c['rabbit'] is None for c in data['compartments']))

    def test_invalid_compartment_count_and_duplicate_name(self):
        self.assertEqual(self._create_cage(rows_count=0).status_code, 400)
        self.assertEqual(self._create_cage(rows_count=99).status_code, 400)
        self.assertEqual(self._create_cage().status_code, 201)
        self.assertEqual(self._create_cage(name='a1').status_code, 400)

    def test_assign_rabbit_to_compartment(self):
        cage = self._create_cage().data['data']
        res = self.client.patch(
            f"/api/farm/rabbits/{self.r1.id}/", {'cage': cage['id'], 'compartment_number': 2}, format='json'
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['cage_number'], 'A1-2')
        detail = self.client.get(f"/api/farm/cages/{cage['id']}/").data['data']
        self.assertEqual(detail['occupied_count'], 1)
        self.assertEqual(detail['compartments'][1]['rabbit']['name'], 'Flash')

    def test_several_rabbits_can_share_a_compartment(self):
        cage = self._create_cage().data['data']
        for rabbit in (self.r1, self.r2):
            res = self.client.patch(
                f"/api/farm/rabbits/{rabbit.id}/", {'cage': cage['id'], 'compartment_number': 1}, format='json'
            )
            self.assertEqual(res.status_code, 200, res.content)
            self.assertEqual(res.data['data']['cage_number'], 'A1-1')

        detail = self.client.get(f"/api/farm/cages/{cage['id']}/").data['data']
        first = detail['compartments'][0]
        self.assertCountEqual([r['name'] for r in first['rabbits']], ['Flash', 'Bella'])
        self.assertIn(first['rabbit']['name'], ['Flash', 'Bella'])  # champ conservé pour compatibilité
        self.assertEqual(detail['compartments'][1]['rabbits'], [])
        self.assertEqual(detail['occupied_count'], 1, 'une loge partagée ne compte qu\'une fois')
        self.assertEqual(detail['rabbits_count'], 2)

    def test_moving_one_rabbit_out_keeps_the_other(self):
        cage = self._create_cage().data['data']
        for rabbit in (self.r1, self.r2):
            self.client.patch(f"/api/farm/rabbits/{rabbit.id}/", {'cage': cage['id'], 'compartment_number': 2}, format='json')
        self.client.patch(f"/api/farm/rabbits/{self.r1.id}/", {'cage': None, 'compartment_number': None}, format='json')
        detail = self.client.get(f"/api/farm/cages/{cage['id']}/").data['data']
        self.assertEqual([r['name'] for r in detail['compartments'][1]['rabbits']], ['Bella'])
        self.assertEqual(detail['rabbits_count'], 1)

    def test_cannot_overflow_or_omit_compartment(self):
        cage = self._create_cage().data['data']
        url = f"/api/farm/rabbits/{self.r1.id}/"
        self.assertEqual(self.client.patch(url, {'cage': cage['id'], 'compartment_number': 1}, format='json').status_code, 200)
        url2 = f"/api/farm/rabbits/{self.r2.id}/"
        self.assertEqual(self.client.patch(url2, {'cage': cage['id'], 'compartment_number': 4}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url2, {'cage': cage['id']}, format='json').status_code, 400)

    def test_cannot_use_foreign_cage(self):
        foreign = Cage.objects.create(owner=self.other, name='Z9', rows_count=2)
        res = self.client.patch(
            f"/api/farm/rabbits/{self.r1.id}/", {'cage': foreign.id, 'compartment_number': 1}, format='json'
        )
        self.assertEqual(res.status_code, 400)
        self.assertNotEqual(self.client.get(f'/api/farm/cages/{foreign.id}/').status_code, 200)

    def test_cannot_shrink_below_occupied_compartment(self):
        cage = self._create_cage().data['data']
        self.client.patch(
            f"/api/farm/rabbits/{self.r1.id}/", {'cage': cage['id'], 'compartment_number': 3}, format='json'
        )
        res = self.client.patch(f"/api/farm/cages/{cage['id']}/", {'rows_count': 2}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.client.patch(f"/api/farm/cages/{cage['id']}/", {'rows_count': 4}, format='json').status_code, 200)

    def test_grid_of_rows_and_columns(self):
        res = self._create_cage(rows_count=2, columns_count=3)
        self.assertEqual(res.status_code, 201, res.content)
        data = res.data['data']
        self.assertEqual(data['compartments_count'], 6)
        self.assertEqual(
            [(c['number'], c['row'], c['column']) for c in data['compartments']],
            [(1, 1, 1), (2, 1, 2), (3, 1, 3), (4, 2, 1), (5, 2, 2), (6, 2, 3)],
        )
        self.assertEqual(self._create_cage(name='B', columns_count=7).status_code, 400)

    def test_grid_rabbit_in_second_column(self):
        cage = self._create_cage(rows_count=2, columns_count=2).data['data']
        res = self.client.patch(
            f"/api/farm/rabbits/{self.r1.id}/", {'cage': cage['id'], 'compartment_number': 4}, format='json'
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.client.patch(
            f"/api/farm/rabbits/{self.r2.id}/", {'cage': cage['id'], 'compartment_number': 5}, format='json'
        ).status_code, 400)

    def test_cannot_change_columns_when_occupied(self):
        cage = self._create_cage(rows_count=2, columns_count=2).data['data']
        self.client.patch(
            f"/api/farm/rabbits/{self.r1.id}/", {'cage': cage['id'], 'compartment_number': 2}, format='json'
        )
        url = f"/api/farm/cages/{cage['id']}/"
        self.assertEqual(self.client.patch(url, {'columns_count': 3}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'rows_count': 3}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(url, {'rows_count': 1}, format='json').status_code, 200)


class LitterWeaningTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='eleveur3', password='x')
        self.other = User.objects.create_user(username='autre3', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        born = date.today() - timedelta(days=400)
        self.buck = Rabbit.objects.create(owner=self.user, name='Flash', tag_number='M1', gender='M', birth_date=born)
        self.doe = Rabbit.objects.create(
            owner=self.user, name='Bella', tag_number='F1', gender='F', birth_date=born,
            color='Fauve', status=Rabbit.Status.LACTATING,
        )

    def _litter(self, days_ago=10, alive=7, **extra):
        birth = date.today() - timedelta(days=days_ago)
        payload = {
            'mother': self.doe.id, 'father': self.buck.id, 'birth_date': birth.isoformat(),
            'born_alive': alive, 'still_born': 1,
        }
        payload.update(extra)
        res = self.client.post('/api/farm/litters/', payload, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.data['data']

    def _wean(self, litter_id, **body):
        return self.client.post(f'/api/farm/litters/{litter_id}/wean/', body, format='json')

    def _place_doe(self, name='A1', compartment=2):
        cage = Cage.objects.create(owner=self.user, name=name, rows_count=3)
        self.doe.cage = cage
        self.doe.compartment_number = compartment
        self.doe.save()
        return cage

    # --- champs calculés ---------------------------------------------

    def test_litter_exposes_age_remaining_and_status(self):
        litter = self._litter(days_ago=12, alive=7)
        self.assertEqual(litter['age_days'], 12)
        self.assertEqual(litter['kits_remaining'], 7)
        self.assertEqual(litter['days_until_weaning'], 33)
        self.assertEqual(litter['weaning_status'], 'nursing')
        self.assertEqual(litter['died_count'], 0)
        self.assertIsNone(litter['weaned_count'])

    def test_status_becomes_due_when_planned_date_passes(self):
        litter = self._litter(days_ago=50, alive=5)
        self.assertEqual(litter['weaning_status'], 'weaning_due')
        self.assertEqual(litter['days_until_weaning'], -5)

    def test_deaths_reduce_remaining_kits_and_are_validated(self):
        litter = self._litter(alive=7)
        url = f"/api/farm/litters/{litter['id']}/"
        res = self.client.patch(url, {'died_count': 2}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['kits_remaining'], 5)
        self.assertEqual(self.client.patch(url, {'born_alive': 1}, format='json').status_code, 400)

    def test_weaning_fields_cannot_be_forged_through_patch(self):
        litter = self._litter()
        self.client.patch(f"/api/farm/litters/{litter['id']}/", {'weaned_count': 7}, format='json')
        self.assertEqual(self.client.get(f"/api/farm/litters/{litter['id']}/").data['data']['kits_remaining'], 7)

    # --- action wean ------------------------------------------------------

    def test_partial_then_full_weaning_updates_counters_and_mother(self):
        litter = self._litter(alive=7)
        res = self._wean(litter['id'], count=3)
        self.assertEqual(res.status_code, 200, res.content)
        data = res.data['data']['litter']
        self.assertEqual((data['weaned_count'], data['kits_remaining']), (3, 4))
        self.assertEqual(data['weaned_at'], date.today().isoformat())
        self.assertEqual(data['weaning_status'], 'nursing')
        self.doe.refresh_from_db()
        self.assertEqual(self.doe.status, Rabbit.Status.LACTATING)

        res = self._wean(litter['id'], count=4, weaned_at=(date.today() - timedelta(days=1)).isoformat())
        self.assertEqual(res.status_code, 200, res.content)
        data = res.data['data']['litter']
        self.assertEqual((data['weaned_count'], data['kits_remaining'], data['weaning_status']), (7, 0, 'weaned'))
        self.doe.refresh_from_db()
        self.assertEqual(self.doe.status, Rabbit.Status.ACTIVE)

    def test_cannot_wean_more_than_remaining_or_nothing(self):
        litter = self._litter(alive=4)
        for count in (0, 5, 'abc', None):
            self.assertEqual(self._wean(litter['id'], count=count).status_code, 400, count)
        self._wean(litter['id'], count=4)
        self.assertEqual(self._wean(litter['id'], count=1).status_code, 400)

    def test_wean_date_validation(self):
        litter = self._litter(days_ago=10)
        before_birth = (date.today() - timedelta(days=30)).isoformat()
        self.assertEqual(self._wean(litter['id'], count=1, weaned_at=before_birth).status_code, 400)
        self.assertEqual(self._wean(litter['id'], count=1, weaned_at='pas une date').status_code, 400)

    def test_weaning_creates_rabbit_records_linked_to_parents_and_in_mothers_compartment(self):
        cage = self._place_doe(compartment=2)
        litter = self._litter(alive=3)
        res = self._wean(litter['id'], count=2, rabbits=[
            {'name': 'Petit 1', 'tag_number': 'K1', 'gender': 'M'},
            {'name': 'Petit 2', 'tag_number': 'K2', 'gender': 'F', 'color': 'Blanc'},
        ])
        self.assertEqual(res.status_code, 200, res.content)
        created = res.data['data']['rabbits']
        self.assertEqual(len(created), 2)
        kid = Rabbit.objects.get(tag_number='K1')
        self.assertEqual((kid.sire_id, kid.dam_id, kid.owner_id), (self.buck.id, self.doe.id, self.user.id))
        self.assertEqual(kid.birth_date.isoformat(), litter['birth_date'])
        self.assertEqual((kid.cage_id, kid.compartment_number), (cage.id, 2))
        self.assertEqual(kid.color, 'Fauve', 'couleur de la mère par défaut')
        self.assertEqual(Rabbit.objects.get(tag_number='K2').color, 'Blanc')

    def test_weaning_is_atomic_when_a_record_is_invalid(self):
        litter = self._litter(alive=3)
        Rabbit.objects.create(owner=self.user, name='Pris', tag_number='K1', gender='F',
                              birth_date=date.today() - timedelta(days=100))
        res = self._wean(litter['id'], count=2, rabbits=[
            {'name': 'Petit 1', 'tag_number': 'K9', 'gender': 'M'},
            {'name': 'Petit 2', 'tag_number': 'K1', 'gender': 'F'},  # bague déjà utilisée
        ])
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('1', res.data['errors']['rabbits'])
        self.assertFalse(Rabbit.objects.filter(tag_number='K9').exists(), 'rien n\'est créé')
        self.assertEqual(self.client.get(f"/api/farm/litters/{litter['id']}/").data['data']['kits_remaining'], 3)

    def test_records_count_must_match_and_gender_is_required(self):
        litter = self._litter(alive=3)
        one = [{'name': 'A', 'tag_number': 'K1', 'gender': 'M'}]
        self.assertEqual(self._wean(litter['id'], count=2, rabbits=one).status_code, 400)
        self.assertEqual(self._wean(litter['id'], count=1, rabbits=[{'name': 'A', 'tag_number': 'K1'}]).status_code, 400)

    def test_mother_stays_lactating_while_another_litter_is_at_the_nest(self):
        first = self._litter(days_ago=30, alive=2)
        self._litter(days_ago=3, alive=5)
        self._wean(first['id'], count=2)
        self.doe.refresh_from_db()
        self.assertEqual(self.doe.status, Rabbit.Status.LACTATING)

    def test_cannot_wean_someone_elses_litter(self):
        litter = self._litter()
        stranger = APIClient()
        stranger.force_authenticate(self.other)
        res = stranger.post(f"/api/farm/litters/{litter['id']}/wean/", {'count': 1}, format='json')
        self.assertEqual(res.status_code, 404)

    # --- lapereaux, lapine et cage ----------------------------------------

    def test_rabbit_and_cage_report_nursing_kits(self):
        cage = self._place_doe(compartment=2)
        self._litter(alive=7)
        self._litter(days_ago=30, alive=3)  # deuxième portée au nid : elles s'additionnent
        rabbit = self.client.get(f'/api/farm/rabbits/{self.doe.id}/').data['data']
        self.assertEqual(rabbit['nursing_kits'], 10)
        self.assertEqual(self.client.get(f'/api/farm/rabbits/{self.buck.id}/').data['data']['nursing_kits'], 0)

        detail = self.client.get(f'/api/farm/cages/{cage.id}/').data['data']
        self.assertEqual(detail['kits_count'], 10)
        occupant = detail['compartments'][1]['rabbits'][0]
        self.assertEqual((occupant['name'], occupant['nursing_kits']), ('Bella', 10))
        self.assertEqual(detail['compartments'][0]['rabbits'], [])

    def test_kits_follow_the_mother_when_she_moves(self):
        first = self._place_doe(name='A1', compartment=1)
        second = Cage.objects.create(owner=self.user, name='B2', rows_count=2)
        litter = self._litter(alive=6)
        self.assertEqual(self.client.get(f'/api/farm/cages/{first.id}/').data['data']['kits_count'], 6)

        res = self.client.patch(
            f'/api/farm/rabbits/{self.doe.id}/', {'cage': second.id, 'compartment_number': 2}, format='json'
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.client.get(f'/api/farm/cages/{first.id}/').data['data']['kits_count'], 0)
        moved = self.client.get(f'/api/farm/cages/{second.id}/').data['data']
        self.assertEqual(moved['kits_count'], 6)
        self.assertEqual(moved['compartments'][1]['rabbits'][0]['nursing_kits'], 6)
        # la portée expose la nouvelle position de sa mère
        data = self.client.get(f"/api/farm/litters/{litter['id']}/").data['data']
        self.assertEqual((data['mother_cage'], data['mother_compartment']), ('B2', 2))

    def test_weaned_litter_no_longer_counts_in_cage(self):
        cage = self._place_doe()
        litter = self._litter(alive=4)
        self._wean(litter['id'], count=4)
        self.assertEqual(self.client.get(f'/api/farm/cages/{cage.id}/').data['data']['kits_count'], 0)

    def test_duplicate_tag_is_a_validation_error_not_a_crash(self):
        res = self.client.post('/api/farm/rabbits/', {
            'name': 'Doublon', 'tag_number': 'M1', 'gender': 'M',
            'birth_date': (date.today() - timedelta(days=90)).isoformat(),
        }, format='json')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('tag_number', res.data['errors'])
        # renommer un lapin en gardant sa propre bague reste possible
        self.assertEqual(
            self.client.patch(f'/api/farm/rabbits/{self.buck.id}/', {'tag_number': 'M1', 'name': 'Flash II'}, format='json').status_code,
            200,
        )

    def test_birth_date_can_be_entered_after_the_fact(self):
        mating = Mating.objects.create(
            owner=self.user, male=self.buck, female=self.doe,
            mating_date=date.today() - timedelta(days=40),
        )
        birth = date.today() - timedelta(days=6)
        res = self.client.post('/api/farm/litters/', {
            'mating': mating.id, 'birth_date': birth.isoformat(), 'born_alive': 6,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        data = res.data['data']
        self.assertEqual((data['birth_date'], data['age_days']), (birth.isoformat(), 6))
        # le sevrage prévu se calcule depuis la vraie date de naissance
        self.assertEqual(data['weaning_date'], (birth + timedelta(days=45)).isoformat())

    def test_birth_date_cannot_be_in_the_future_or_before_mating(self):
        mating = Mating.objects.create(
            owner=self.user, male=self.buck, female=self.doe,
            mating_date=date.today() - timedelta(days=10),
        )
        future = (date.today() + timedelta(days=1)).isoformat()
        before = (date.today() - timedelta(days=20)).isoformat()
        for value in (future, before):
            res = self.client.post('/api/farm/litters/', {
                'mating': mating.id, 'birth_date': value, 'born_alive': 4,
            }, format='json')
            self.assertEqual(res.status_code, 400, value)
            self.assertIn('birth_date', res.data['errors'])


class MatingWorkflowTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='eleveur4', password='x')
        self.other = User.objects.create_user(username='autre4', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        born = date.today() - timedelta(days=400)
        self.buck = Rabbit.objects.create(owner=self.user, name='Flash', tag_number='M1', gender='M', birth_date=born)
        self.doe = Rabbit.objects.create(owner=self.user, name='Bella', tag_number='F1', gender='F', birth_date=born)

    def _mating(self, days_ago=15):
        res = self.client.post('/api/farm/matings/', {
            'male': self.buck.id, 'female': self.doe.id,
            'mating_date': (date.today() - timedelta(days=days_ago)).isoformat(),
        }, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.data['data']

    # --- palpation ---------------------------------------------------

    def test_palpation_confirms_the_pregnancy(self):
        mating = self._mating()
        res = self.client.post(f"/api/farm/matings/{mating['id']}/palpation/", {}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        data = res.data['data']
        self.assertEqual(data['status'], 'confirmed')
        self.assertEqual(data['palpation_done_at'], date.today().isoformat())
        self.doe.refresh_from_db()
        self.assertEqual(self.doe.status, Rabbit.Status.PREGNANT)

    def test_palpation_with_an_explicit_date_and_its_bounds(self):
        mating = self._mating(days_ago=15)
        url = f"/api/farm/matings/{mating['id']}/palpation/"
        too_early = (date.today() - timedelta(days=30)).isoformat()
        future = (date.today() + timedelta(days=1)).isoformat()
        for value in (too_early, future, 'nimporte quoi'):
            self.assertEqual(self.client.post(url, {'done_at': value}, format='json').status_code, 400, value)
        ok = (date.today() - timedelta(days=3)).isoformat()
        res = self.client.post(url, {'done_at': ok}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['palpation_done_at'], ok)

    def test_palpation_only_while_pending_and_not_forgeable(self):
        mating = self._mating()
        url = f"/api/farm/matings/{mating['id']}/palpation/"
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 200)
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 400, 'déjà confirmée')
        # la date de palpation ne se modifie pas par PATCH
        self.client.patch(f"/api/farm/matings/{mating['id']}/", {'palpation_done_at': '2020-01-01'}, format='json')
        self.assertEqual(
            self.client.get(f"/api/farm/matings/{mating['id']}/").data['data']['palpation_done_at'],
            date.today().isoformat(),
        )

    # --- annulation --------------------------------------------------

    def test_cancel_marks_failed_frees_the_female_and_keeps_the_reason(self):
        mating = self._mating()
        self.doe.refresh_from_db()
        self.assertEqual(self.doe.status, Rabbit.Status.PREGNANT)

        res = self.client.post(f"/api/farm/matings/{mating['id']}/cancel/", {'reason': 'Non gestante à la palpation'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['status'], 'failed')
        self.assertIn('Échec : Non gestante à la palpation', res.data['data']['notes'])
        self.doe.refresh_from_db()
        self.assertEqual(self.doe.status, Rabbit.Status.ACTIVE)

    def test_cancel_keeps_the_female_pregnant_if_another_mating_is_active(self):
        first = self._mating(days_ago=20)
        self._mating(days_ago=2)
        self.client.post(f"/api/farm/matings/{first['id']}/cancel/", {}, format='json')
        self.doe.refresh_from_db()
        self.assertEqual(self.doe.status, Rabbit.Status.PREGNANT)

    def test_cancel_after_palpation_and_not_once_finished(self):
        mating = self._mating()
        self.client.post(f"/api/farm/matings/{mating['id']}/palpation/", {}, format='json')
        url = f"/api/farm/matings/{mating['id']}/cancel/"
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 200)
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 400)

    def test_other_users_cannot_act_on_a_mating(self):
        mating = self._mating()
        stranger = APIClient()
        stranger.force_authenticate(self.other)
        for action in ('palpation', 'cancel'):
            self.assertEqual(stranger.post(f"/api/farm/matings/{mating['id']}/{action}/", {}, format='json').status_code, 404)

    # --- règle des 21 jours pour la mise bas -----------------------------

    def _kindle(self, mating_id, birth):
        return self.client.post('/api/farm/litters/', {
            'mating': mating_id, 'birth_date': birth.isoformat(), 'born_alive': 6,
        }, format='json')

    def test_kindling_needs_at_least_21_days_after_mating(self):
        mating = self._mating(days_ago=20)
        res = self._kindle(mating['id'], date.today())
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('21 jours', str(res.data['errors']['birth_date']))

        mating = self.client.post('/api/farm/matings/', {
            'male': self.buck.id, 'female': self.doe.id,
            'mating_date': (date.today() - timedelta(days=21)).isoformat(),
        }, format='json').data['data']
        self.assertEqual(self._kindle(mating['id'], date.today()).status_code, 201)

    def test_kindling_exactly_21_days_after_a_past_mating(self):
        mating_date = date.today() - timedelta(days=40)
        mating = self.client.post('/api/farm/matings/', {
            'male': self.buck.id, 'female': self.doe.id, 'mating_date': mating_date.isoformat(),
        }, format='json').data['data']
        self.assertEqual(self._kindle(mating['id'], mating_date + timedelta(days=20)).status_code, 400)
        self.assertEqual(self._kindle(mating['id'], mating_date + timedelta(days=21)).status_code, 201)


class CareTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='eleveur', password='x')
        self.other = User.objects.create_user(username='autre', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        born = date.today() - timedelta(days=400)
        self.flash = Rabbit.objects.create(owner=self.user, name='Flash', tag_number='M1', gender='M', birth_date=born)
        self.bella = Rabbit.objects.create(owner=self.user, name='Bella', tag_number='F1', gender='F', birth_date=born)
        self.luna = Rabbit.objects.create(owner=self.user, name='Luna', tag_number='F2', gender='F', birth_date=born)
        self.foreign = Rabbit.objects.create(owner=self.other, name='Intrus', tag_number='X1', gender='M', birth_date=born)

    def _treatment(self, name='Vaccin VHD2', renewal_days=180, **extra):
        payload = {'name': name, 'category': 'vaccine', 'renewal_days': renewal_days}
        payload.update(extra)
        res = self.client.post('/api/farm/care-treatments/', payload, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.data['data']

    def _record(self, treatment, rabbits, days_ago=0, **extra):
        payload = {
            'treatment': treatment['id'],
            'rabbits': [r.id for r in rabbits],
            'date': str(date.today() - timedelta(days=days_ago)),
            'purpose': 'Prévention VHD',
        }
        payload.update(extra)
        res = self.client.post('/api/farm/care-records/', payload, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.data['data']

    def _upcoming(self):
        res = self.client.get('/api/farm/care-records/upcoming/')
        self.assertEqual(res.status_code, 200, res.content)
        return res.data['data']

    def test_treatment_name_must_be_unique_per_owner(self):
        self._treatment()
        res = self.client.post('/api/farm/care-treatments/', {'name': 'vaccin vhd2'}, format='json')
        self.assertEqual(res.status_code, 400)
        # un autre éleveur peut utiliser le même nom
        other = APIClient()
        other.force_authenticate(self.other)
        res = other.post('/api/farm/care-treatments/', {'name': 'Vaccin VHD2'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)

    def test_treatments_are_isolated_between_owners(self):
        self._treatment()
        other = APIClient()
        other.force_authenticate(self.other)
        res = other.get('/api/farm/care-treatments/?all=true')
        self.assertEqual(res.data['data'], [])

    def test_record_computes_next_due_date_and_lists_rabbits(self):
        treatment = self._treatment(renewal_days=30)
        record = self._record(treatment, [self.flash, self.bella], days_ago=10)
        self.assertEqual(record['next_due_date'], str(date.today() + timedelta(days=20)))
        self.assertEqual(record['days_until_due'], 20)
        self.assertEqual(sorted(r['name'] for r in record['rabbits_detail']), ['Bella', 'Flash'])

    def test_one_off_treatment_has_no_due_date(self):
        treatment = self._treatment(name='Bilan', renewal_days=None)
        record = self._record(treatment, [self.flash])
        self.assertIsNone(record['next_due_date'])
        self.assertEqual(self._upcoming(), [])

    def test_record_requires_rabbits_and_rejects_foreign_ones(self):
        treatment = self._treatment()
        res = self.client.post('/api/farm/care-records/', {
            'treatment': treatment['id'], 'rabbits': [], 'date': str(date.today()),
        }, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client.post('/api/farm/care-records/', {
            'treatment': treatment['id'], 'rabbits': [self.foreign.id], 'date': str(date.today()),
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_record_cannot_use_foreign_treatment_or_future_date(self):
        other = APIClient()
        other.force_authenticate(self.other)
        foreign_treatment = other.post('/api/farm/care-treatments/', {'name': 'Secret'}, format='json').data['data']
        res = self.client.post('/api/farm/care-records/', {
            'treatment': foreign_treatment['id'], 'rabbits': [self.flash.id], 'date': str(date.today()),
        }, format='json')
        self.assertEqual(res.status_code, 400)

        treatment = self._treatment()
        res = self.client.post('/api/farm/care-records/', {
            'treatment': treatment['id'], 'rabbits': [self.flash.id],
            'date': str(date.today() + timedelta(days=1)),
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_upcoming_flags_overdue_soon_and_upcoming(self):
        overdue = self._treatment(name='Vermifuge', renewal_days=30)
        soon = self._treatment(name='Vitamine', renewal_days=30)
        later = self._treatment(name='Vaccin', renewal_days=180)
        self._record(overdue, [self.flash], days_ago=40)   # échu il y a 10 j
        self._record(soon, [self.bella], days_ago=25)      # dans 5 j
        self._record(later, [self.luna], days_ago=0)       # dans 180 j

        items = self._upcoming()
        self.assertEqual([i['treatment_name'] for i in items], ['Vermifuge', 'Vitamine', 'Vaccin'])
        self.assertEqual([i['status'] for i in items], ['overdue', 'soon', 'upcoming'])
        self.assertEqual(items[0]['days_until_due'], -10)
        self.assertEqual(items[1]['days_until_due'], 5)

    def test_renewal_replaces_previous_due_date_for_that_rabbit_only(self):
        treatment = self._treatment(renewal_days=30)
        self._record(treatment, [self.flash, self.bella], days_ago=40)  # les deux en retard
        self._record(treatment, [self.flash], days_ago=0)                # Flash renouvelé

        items = self._upcoming()
        by_status = {i['status']: i for i in items}
        self.assertEqual([r['name'] for r in by_status['overdue']['rabbits']], ['Bella'])
        self.assertEqual([r['name'] for r in by_status['upcoming']['rabbits']], ['Flash'])

    def test_retired_rabbits_are_not_reminded(self):
        treatment = self._treatment(renewal_days=30)
        self._record(treatment, [self.flash, self.bella], days_ago=40)
        self.bella.status = Rabbit.Status.RETIRED
        self.bella.save()
        items = self._upcoming()
        self.assertEqual(len(items), 1)
        self.assertEqual([r['name'] for r in items[0]['rabbits']], ['Flash'])

    def test_upcoming_is_isolated_between_owners(self):
        treatment = self._treatment(renewal_days=30)
        self._record(treatment, [self.flash], days_ago=40)
        other = APIClient()
        other.force_authenticate(self.other)
        res = other.get('/api/farm/care-records/upcoming/')
        self.assertEqual(res.data['data'], [])

    def test_editing_date_recomputes_due_date(self):
        treatment = self._treatment(renewal_days=30)
        record = self._record(treatment, [self.flash], days_ago=0)
        new_date = date.today() - timedelta(days=10)
        res = self.client.patch(f"/api/farm/care-records/{record['id']}/", {'date': str(new_date)}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['next_due_date'], str(new_date + timedelta(days=30)))

    def test_used_treatment_cannot_be_deleted(self):
        treatment = self._treatment()
        record = self._record(treatment, [self.flash])
        res = self.client.delete(f"/api/farm/care-treatments/{treatment['id']}/")
        self.assertEqual(res.status_code, 400, res.content)
        self.client.delete(f"/api/farm/care-records/{record['id']}/")
        res = self.client.delete(f"/api/farm/care-treatments/{treatment['id']}/")
        self.assertEqual(res.status_code, 200, res.content)

    def test_filter_records_by_rabbit(self):
        treatment = self._treatment()
        self._record(treatment, [self.flash])
        self._record(treatment, [self.bella])
        res = self.client.get(f'/api/farm/care-records/?all=true&rabbits={self.bella.id}')
        self.assertEqual(len(res.data['data']), 1)
        self.assertEqual(res.data['data'][0]['rabbits'], [self.bella.id])


class OfflineSyncTests(APITestCase):
    """
    Garde-fous nécessaires à la synchronisation hors-ligne du mobile :
    créations idempotentes (retry réseau après coupure) et suppression douce
    (pour que le pull de synchro détecte les suppressions).
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='eleveur-sync', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.born = date.today() - timedelta(days=400)

    def test_repeated_create_with_same_client_uuid_is_idempotent(self):
        client_uuid = str(uuid.uuid4())
        payload = {
            'name': 'Flash', 'tag_number': 'M1', 'gender': 'M',
            'birth_date': str(self.born), 'client_uuid': client_uuid,
        }
        first = self.client.post('/api/farm/rabbits/', payload, format='json')
        self.assertEqual(first.status_code, 201, first.content)

        # Retry réseau : même client_uuid renvoyé une seconde fois, pas de doublon créé.
        second = self.client.post('/api/farm/rabbits/', payload, format='json')
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.data['data']['id'], second.data['data']['id'])
        self.assertEqual(Rabbit.objects.filter(owner=self.user, tag_number='M1').count(), 1)

    def test_deleted_rabbit_is_soft_deleted_and_hidden_by_default(self):
        rabbit = Rabbit.objects.create(
            owner=self.user, name='Flash', tag_number='M1', gender='M', birth_date=self.born
        )
        res = self.client.delete(f'/api/farm/rabbits/{rabbit.id}/')
        self.assertEqual(res.status_code, 200, res.content)

        # Toujours en base (tombstone), mais masqué de la liste par défaut...
        self.assertEqual(Rabbit.objects.filter(pk=rabbit.id, is_deleted=True).count(), 1)
        listed = self.client.get('/api/farm/rabbits/?all=true').data['data']
        self.assertNotIn(rabbit.id, [r['id'] for r in listed])

        # ...et visible pour le pull de synchro qui a besoin de détecter la suppression.
        with_deleted = self.client.get('/api/farm/rabbits/?all=true&include_deleted=true').data['data']
        self.assertIn(rabbit.id, [r['id'] for r in with_deleted])

    def test_soft_deleted_rabbit_frees_its_cage_compartment(self):
        cage = Cage.objects.create(owner=self.user, name='A1', rows_count=2)
        rabbit = Rabbit.objects.create(
            owner=self.user, name='Flash', tag_number='M1', gender='M', birth_date=self.born,
            cage=cage, compartment_number=1,
        )
        self.client.delete(f'/api/farm/rabbits/{rabbit.id}/')
        detail = self.client.get(f'/api/farm/cages/{cage.id}/').data['data']
        self.assertEqual(detail['occupied_count'], 0)
        self.assertEqual(detail['compartments'][0]['rabbit'], None)
