from django.core.management.base import BaseCommand

from pharmacy.models import Medication, Pharmacy, PharmacyMedication


class Command(BaseCommand):
    help = "Peuple le catalogue pharmacie (médicaments, pharmacies, prix) avec des données fictives réalistes."

    def handle(self, *args, **options):
        medications_data = [
            ("Ivermectine 1%", Medication.Category.ANTIPARASITIC, "Traitement des gales et parasites externes."),
            ("VHD2 - Vaccin viral hémorragique", Medication.Category.VACCINE, "Vaccin contre la maladie virale hémorragique du lapin."),
            ("Myxomatose - Vaccin", Medication.Category.VACCINE, "Vaccin contre la myxomatose."),
            ("Baytril 2.5%", Medication.Category.ANTIBIOTIC, "Antibiotique à large spectre."),
            ("Vitamine ADE Injectable", Medication.Category.VITAMIN, "Complexe vitaminé pour reproducteurs."),
            ("Primpéran (anti-stase digestive)", Medication.Category.DIGESTIVE, "Stimulant du transit digestif."),
        ]
        medications = {}
        for name, category, description in medications_data:
            med, created = Medication.objects.get_or_create(
                name=name, defaults={'category': category, 'description': description}
            )
            medications[name] = med
            self.stdout.write(self.style.SUCCESS(f"Médicament {med.name} [{'créé' if created else 'existant'}]"))

        pharmacies_data = [
            ("Pharmacie Vétérinaire du Plateau", "Boulevard de la République, Abidjan", "+2250102030405", 5.3197, -4.0227),
            ("Clinique Vétérinaire Riviera", "Rue des Jardins, Abidjan", "+2250506070809", 5.3450, -3.9850),
            ("Pharmacie Agro-Vet Yamoussoukro", "Avenue Houphouët-Boigny, Yamoussoukro", "+2250708091011", 6.8205, -5.2767),
            ("Pharmacie Rurale de Bouaké", "Marché central, Bouaké", "+2250910111213", 7.6938, -5.0300),
        ]
        pharmacies = {}
        for name, address, phone, lat, lng in pharmacies_data:
            pharm, created = Pharmacy.objects.get_or_create(
                name=name, defaults={'address': address, 'phone': phone, 'latitude': lat, 'longitude': lng}
            )
            pharmacies[name] = pharm
            self.stdout.write(self.style.SUCCESS(f"Pharmacie {pharm.name} [{'créée' if created else 'existante'}]"))

        # Prix variés pour que la bande min/max soit visible, et une pharmacie qui ne
        # vend pas tout (pour tester le cas "pharmacie absente de la liste d'un médicament").
        prices = [
            ("Ivermectine 1%", "Pharmacie Vétérinaire du Plateau", 4500),
            ("Ivermectine 1%", "Clinique Vétérinaire Riviera", 5200),
            ("Ivermectine 1%", "Pharmacie Agro-Vet Yamoussoukro", 4800),
            ("VHD2 - Vaccin viral hémorragique", "Pharmacie Vétérinaire du Plateau", 3000),
            ("VHD2 - Vaccin viral hémorragique", "Clinique Vétérinaire Riviera", 3500),
            ("Myxomatose - Vaccin", "Clinique Vétérinaire Riviera", 2800),
            ("Myxomatose - Vaccin", "Pharmacie Rurale de Bouaké", 2600),
            ("Baytril 2.5%", "Pharmacie Agro-Vet Yamoussoukro", 6000),
            ("Vitamine ADE Injectable", "Pharmacie Vétérinaire du Plateau", 1500),
            ("Vitamine ADE Injectable", "Pharmacie Rurale de Bouaké", 1200),
            ("Vitamine ADE Injectable", "Clinique Vétérinaire Riviera", 1800),
            # "Primpéran" volontairement non vendu par aucune pharmacie -> teste le cas price_min/max = None.
        ]
        for med_name, pharm_name, price in prices:
            PharmacyMedication.objects.get_or_create(
                medication=medications[med_name], pharmacy=pharmacies[pharm_name],
                defaults={'price': price},
            )

        self.stdout.write(self.style.SUCCESS("Données pharmacie initialisées."))
