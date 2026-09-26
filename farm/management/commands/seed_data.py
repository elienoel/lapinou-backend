from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from farm.models import Breed, Rabbit, Mating, Litter, CareEvent, FinanceTransaction
from community.models import Post, Comment, PostLike

User = get_user_model()


class Command(BaseCommand):
    help = "Peuple la base de données avec des données initiales réalistes pour l'élevage de lapins et la communauté."

    def add_arguments(self, parser):
        parser.add_argument(
            '--phone',
            type=str,
            default='+2250700000000',
            help="Numéro de téléphone de l'éleveur à associer aux données."
        )

    def handle(self, *args, **options):
        phone = options['phone'].strip()
        self.stdout.write(self.style.NOTICE(f"Initialisation du seeding pour l'éleveur {phone}..."))

        # 1. Utilisateur principal (Éleveur)
        user, created = User.objects.get_or_create(
            phone_number=phone,
            defaults={
                'username': f"eleveur_{phone.replace('+', '')[-6:]}",
                'first_name': 'Élie',
                'last_name': 'Noël',
                'farm_name': 'Clapier du Val Fleuri',
                'location': 'Abidjan, Côte d\'Ivoire',
                'bio': 'Éleveur passionné de lapins de race pure (Fauve de Bourgogne, Néo-Zélandais, Géant des Flandres).',
            }
        )
        if not user.farm_name:
            user.farm_name = 'Clapier du Val Fleuri'
            user.save(update_fields=['farm_name'])

        status_user = "créé" if created else "existant"
        self.stdout.write(self.style.SUCCESS(f"✔ Utilisateur {user.username} ({user.phone_number}) [{status_user}]"))

        # Éleveur secondaire pour animer la communauté
        user_community, _ = User.objects.get_or_create(
            phone_number='+2250500112233',
            defaults={
                'username': 'mamadou_diallo',
                'first_name': 'Mamadou',
                'last_name': 'Diallo',
                'farm_name': 'Élevage Cunico-Diallo',
                'location': 'Yamoussoukro, Côte d\'Ivoire',
                'bio': 'Spécialiste de la cuniculiculture en climat tropical.',
            }
        )

        # 2. Races de lapins (Breeds)
        breeds_data = [
            ("Fauve de Bourgogne", "Race moyenne très rustique, excellente qualité bouchère et très prolifique.", 31),
            ("Néo-Zélandais", "Lapin blanc albinos à croissance très rapide, très utilisé en élevage commercial.", 31),
            ("Géant des Flandres", "Une des plus grandes races de lapins, animaux calmes et imposants.", 32),
            ("Californien", "Corps blanc avec extrémités foncées (museau, oreilles, pattes), très résistant.", 31),
            ("Rex", "Fourrure veloutée unique très douce et dense.", 31),
            ("Papillon Français", "Robe blanche tachetée de noir caractéristique, très vigoureux.", 31),
            ("Argenté de Champagne", "Fourrure argentée réputée pour sa viande savoureuse.", 31),
        ]
        created_breeds = {}
        for name, desc, gest in breeds_data:
            b, _ = Breed.objects.get_or_create(
                name=name,
                defaults={'description': desc, 'average_gestation_days': gest}
            )
            created_breeds[name] = b
        self.stdout.write(self.style.SUCCESS(f"✔ {len(created_breeds)} races enregistrées"))

        today = date.today()

        # 3. Lapins avec filiation et généalogie 3 générations
        fb_breed = created_breeds["Fauve de Bourgogne"]
        gf_breed = created_breeds["Géant des Flandres"]
        nz_breed = created_breeds["Néo-Zélandais"]

        # Génération 1 : Grands-parents
        titan, _ = Rabbit.objects.get_or_create(
            owner=user,
            tag_number="FB-2022-01",
            defaults={
                'name': 'Titan',
                'gender': Rabbit.Gender.MALE,
                'breed': fb_breed,
                'birth_date': today - timedelta(days=850),
                'color': 'Fauve chaud',
                'cage_number': 'A-01',
                'status': Rabbit.Status.ACTIVE,
                'weight_kg': 4.80,
                'avatar_color_index': 0,
                'notes': 'Grand reproducteur champion de race, très docile et robuste.',
            }
        )

        sultane, _ = Rabbit.objects.get_or_create(
            owner=user,
            tag_number="FB-2022-02",
            defaults={
                'name': 'Sultane',
                'gender': Rabbit.Gender.FEMALE,
                'breed': fb_breed,
                'birth_date': today - timedelta(days=820),
                'color': 'Fauve unicolore',
                'cage_number': 'A-02',
                'status': Rabbit.Status.ACTIVE,
                'weight_kg': 4.60,
                'avatar_color_index': 1,
                'notes': 'Excellente laitière, portées régulières de 8 à 10 lapereaux.',
            }
        )

        goliath, _ = Rabbit.objects.get_or_create(
            owner=user,
            tag_number="GF-2022-05",
            defaults={
                'name': 'Goliath',
                'gender': Rabbit.Gender.MALE,
                'breed': gf_breed,
                'birth_date': today - timedelta(days=800),
                'color': 'Gris garenne',
                'cage_number': 'A-03',
                'status': Rabbit.Status.ACTIVE,
                'weight_kg': 6.20,
                'avatar_color_index': 2,
                'notes': 'Géniteur géant pour améliorer le gabarit des hybrides.',
            }
        )

        perle, _ = Rabbit.objects.get_or_create(
            owner=user,
            tag_number="NZ-2022-08",
            defaults={
                'name': 'Perle',
                'gender': Rabbit.Gender.FEMALE,
                'breed': nz_breed,
                'birth_date': today - timedelta(days=780),
                'color': 'Blanc pur',
                'cage_number': 'A-04',
                'status': Rabbit.Status.ACTIVE,
                'weight_kg': 4.50,
                'avatar_color_index': 3,
                'notes': 'Mère prolifique, tempérament calme.',
            }
        )

        # Génération 2 : Parents (Fils et Filles)
        flash, _ = Rabbit.objects.get_or_create(
            owner=user,
            tag_number="FB-2023-11",
            defaults={
                'name': 'Flash',
                'gender': Rabbit.Gender.MALE,
                'breed': fb_breed,
                'birth_date': today - timedelta(days=450),
                'color': 'Fauve doré',
                'cage_number': 'B-01',
                'status': Rabbit.Status.ACTIVE,
                'weight_kg': 4.50,
                'sire': titan,
                'dam': sultane,
                'avatar_color_index': 0,
                'notes': 'Mâle reproducteur vif, très bonne conformation dorsale.',
            }
        )

        bella, _ = Rabbit.objects.get_or_create(
            owner=user,
            tag_number="FB-2023-12",
            defaults={
                'name': 'Bella',
                'gender': Rabbit.Gender.FEMALE,
                'breed': fb_breed,
                'birth_date': today - timedelta(days=420),
                'color': 'Fauve fauve',
                'cage_number': 'B-02',
                'status': Rabbit.Status.PREGNANT,
                'weight_kg': 4.30,
                'sire': goliath,
                'dam': perle,
                'avatar_color_index': 1,
                'notes': 'Femelle en gestation confirmée. Bonne prise de nidification.',
            }
        )

        etoile, _ = Rabbit.objects.get_or_create(
            owner=user,
            tag_number="NZ-2023-15",
            defaults={
                'name': 'Étoile',
                'gender': Rabbit.Gender.FEMALE,
                'breed': nz_breed,
                'birth_date': today - timedelta(days=390),
                'color': 'Blanc albinos',
                'cage_number': 'B-03',
                'status': Rabbit.Status.LACTATING,
                'weight_kg': 4.20,
                'avatar_color_index': 2,
                'notes': 'En cours d\'allaitement au nid (portée de 7 lapereaux).',
            }
        )

        # Génération 3 : Jeunes reproducteurs
        caramel, _ = Rabbit.objects.get_or_create(
            owner=user,
            tag_number="FB-2024-03",
            defaults={
                'name': 'Caramel',
                'gender': Rabbit.Gender.MALE,
                'breed': fb_breed,
                'birth_date': today - timedelta(days=180),
                'color': 'Fauve caramel',
                'cage_number': 'C-01',
                'status': Rabbit.Status.ACTIVE,
                'weight_kg': 3.80,
                'sire': flash,
                'dam': bella,
                'avatar_color_index': 0,
                'notes': 'Jeune mâle sélectionné pour la relève du cheptel.',
            }
        )

        luna, _ = Rabbit.objects.get_or_create(
            owner=user,
            tag_number="FB-2024-04",
            defaults={
                'name': 'Luna',
                'gender': Rabbit.Gender.FEMALE,
                'breed': fb_breed,
                'birth_date': today - timedelta(days=180),
                'color': 'Fauve intense',
                'cage_number': 'C-02',
                'status': Rabbit.Status.RESTING,
                'weight_kg': 3.70,
                'sire': flash,
                'dam': bella,
                'avatar_color_index': 3,
                'notes': 'Jeune femelle au repos avant sa première saillie.',
            }
        )
        self.stdout.write(self.style.SUCCESS("✔ 8 lapins reproducteurs créés avec arbre généalogique 3 générations"))

        # 4. Accouplements (Matings)
        mating_gestation_date = today - timedelta(days=27)
        mating_active, _ = Mating.objects.get_or_create(
            owner=user,
            male=flash,
            female=bella,
            mating_date=mating_gestation_date,
            defaults={
                'status': Mating.Status.CONFIRMED,
                'palpation_date': mating_gestation_date + timedelta(days=12),
                'nest_box_date': mating_gestation_date + timedelta(days=28),  # Demain !
                'expected_kindling_date': mating_gestation_date + timedelta(days=31),  # Dans 4 jours
                'notes': '3 sauts validés. Palpation positive confirmée (8 embryons). Pose boîte à nid imminente.',
            }
        )

        mating_past_date = today - timedelta(days=40)
        mating_past, _ = Mating.objects.get_or_create(
            owner=user,
            male=titan,
            female=etoile,
            mating_date=mating_past_date,
            defaults={
                'status': Mating.Status.KINDLED,
                'palpation_date': mating_past_date + timedelta(days=12),
                'nest_box_date': mating_past_date + timedelta(days=28),
                'expected_kindling_date': mating_past_date + timedelta(days=31),
                'notes': 'Mise bas réussie au 31e jour.',
            }
        )
        self.stdout.write(self.style.SUCCESS("✔ 2 accouplements créés (1 gestation en cours J27 et 1 portée née)"))

        # 5. Mises bas (Litters)
        litter_date = today - timedelta(days=9)
        litter_1, _ = Litter.objects.get_or_create(
            owner=user,
            mother=etoile,
            birth_date=litter_date,
            defaults={
                'mating': mating_past,
                'father': titan,
                'born_alive': 7,
                'still_born': 1,
                'weaning_date': litter_date + timedelta(days=45),
                'notes': 'Lapereaux vigoureux et bien nourris. Nid propre avec duvet abondant.',
            }
        )
        self.stdout.write(self.style.SUCCESS("✔ 1 portée au nid enregistrée (7 lapereaux vivants)"))

        # 6. Soins sanitaires (CareEvents)
        CareEvent.objects.get_or_create(
            owner=user,
            rabbit=flash,
            title='Rappel annuel vaccin VHD 1 & 2',
            defaults={
                'care_type': CareEvent.CareType.VACCINE,
                'date': today + timedelta(days=3),
                'reminder_date': today + timedelta(days=2),
                'is_completed': False,
                'notes': 'Vaccin Filavac VHD C+K. Contrôler la température avant injection.',
            }
        )

        CareEvent.objects.get_or_create(
            owner=user,
            rabbit=bella,
            title='Palpation abdominale de gestation',
            defaults={
                'care_type': CareEvent.CareType.CHECKUP,
                'date': today - timedelta(days=15),
                'is_completed': True,
                'notes': 'Palpation effectuée avec succès à J12. Embryons nets.',
            }
        )

        CareEvent.objects.get_or_create(
            owner=user,
            rabbit=caramel,
            title='Cure préventive anti-coccidiose',
            defaults={
                'care_type': CareEvent.CareType.COCCIDIOSIS,
                'date': today + timedelta(days=5),
                'reminder_date': today + timedelta(days=4),
                'is_completed': False,
                'notes': 'Traitement dans l\'eau de boisson pendant 3 jours consécutifs.',
            }
        )
        self.stdout.write(self.style.SUCCESS("✔ 3 soins vétérinaires enregistrés"))

        # 7. Finances (Dépenses et Ventes)
        finances = [
            (FinanceTransaction.TransactionType.INCOME, "Vente 2 jeunes reproducteurs FB", 80.00, today - timedelta(days=3), "Vente reproducteurs", "Vente à l'éleveur Yao d'Abidjan."),
            (FinanceTransaction.TransactionType.INCOME, "Vente 4 lapins de chair préparés", 65.00, today - timedelta(days=7), "Vente viande", "Poids carcasse moyen 1.6kg."),
            (FinanceTransaction.TransactionType.EXPENSE, "Sac 25kg granulés élevage + luzerne", 32.50, today - timedelta(days=5), "Alimentation", "Granulés 17% protéines brutes."),
            (FinanceTransaction.TransactionType.EXPENSE, "Vaccins Filavac VHD (flacon 5 doses)", 45.00, today - timedelta(days=12), "Vétérinaire / Soins", "Acheté à la pharmacie vétérinaire."),
            (FinanceTransaction.TransactionType.EXPENSE, "Foin de Crau dépoussiéré (2 bottes)", 18.00, today - timedelta(days=16), "Litière & Fourrage", "Pour garniture des boîtes à nid."),
        ]
        for tx_type, title, amount, dt, cat, notes in finances:
            FinanceTransaction.objects.get_or_create(
                owner=user,
                title=title,
                date=dt,
                defaults={
                    'transaction_type': tx_type,
                    'amount': amount,
                    'category': cat,
                    'notes': notes,
                }
            )
        self.stdout.write(self.style.SUCCESS("✔ 5 transactions financières enregistrées (+145.00 € / -95.50 €)"))

        # 8. Publications & Discussions Communauté
        post1, _ = Post.objects.get_or_create(
            author=user_community,
            title="Conseils pour l'alimentation en période de forte chaleur ☀️",
            defaults={
                'content': "Bonjour à tous les éleveurs ! Avec les températures élevées en ce moment, pensez à distribuer les granulés très tôt le matin et tard le soir. L'eau fraîche à volonté avec un peu de vinaigre de cidre de pomme aide beaucoup nos lapins à réguler leur température corporelle.",
                'tags': "alimentation,chaleur,santé",
            }
        )

        Comment.objects.get_or_create(
            post=post1,
            author=user,
            content="Merci beaucoup pour ce rappel précieux Mamadou ! J'ajoute aussi des bouteilles d'eau glacée dans les clapiers lors des pics à midi.",
        )

        PostLike.objects.get_or_create(post=post1, user=user)

        post2, _ = Post.objects.get_or_create(
            author=user,
            title="Gestation confirmée chez Bella (Fauve de Bourgogne) 🐰🎉",
            defaults={
                'content': "Palpation très nette à J12 chez Bella issue de la lignée Goliath x Perle. Boîte à nid installée ce matin, mise bas estimée d'ici 4 jours ! Les prédictions de l'application Lapinou facilitent grandement l'organisation.",
                'tags': "mise bas,fauve de bourgogne,reproduction",
            }
        )
        PostLike.objects.get_or_create(post=post2, user=user_community)
        self.stdout.write(self.style.SUCCESS("✔ Fil d'actualité communautaire et commentaires initialisés"))

        self.stdout.write(self.style.SUCCESS("\n🎉 Base de données peuplée avec succès !"))

