"""
Types de soins proposés d'office à chaque nouvel élevage. L'éleveur peut ensuite
les modifier (nom, durée de renouvellement, notes) ou les supprimer.
"""

# (nom, catégorie, jours avant renouvellement ou None pour un soin ponctuel, notes)
DEFAULT_CARE_TREATMENTS = [
    (
        'Vaccin VHD (VHD1 + VHD2)', 'vaccine', 180,
        "Maladie hémorragique virale. Première injection vers 10 semaines, puis rappel tous les 6 mois.",
    ),
    (
        'Vaccin Myxomatose', 'vaccine', 180,
        "Première injection vers 5 à 6 semaines, puis rappel tous les 6 mois.",
    ),
    (
        'Vitamines AD3E', 'vitamin', 30,
        "Dans l'eau de boisson, en cure de quelques jours, surtout pour les reproducteurs.",
    ),
    (
        'Déparasitage interne', 'deworming', 90,
        "Vermifuge (ex. albendazole, fenbendazole) tous les 3 mois.",
    ),
    (
        'Ivermectine (gale, parasites externes)', 'antiparasitic', 90,
        "Contre la gale des oreilles et les parasites externes. Respecter la dose au poids.",
    ),
    (
        'Anti-coccidien', 'coccidiosis', None,
        "Préventif au sevrage (ex. toltrazuril, amprolium) ou en cas de diarrhée.",
    ),
    (
        'Antibiotique', 'antibiotic', None,
        "Uniquement sur avis vétérinaire. Noter le produit et la durée du traitement.",
    ),
]


def create_default_care_treatments(user, treatment_model=None):
    """
    Ajoute les types de soins par défaut à l'élevage de `user`. Un nom déjà présent,
    même supprimé par l'éleveur, n'est jamais recréé.
    """
    if treatment_model is None:
        from .models import CareTreatment as treatment_model
    existing = {
        name.lower()
        for name in treatment_model.objects.filter(owner=user).values_list('name', flat=True)
    }
    treatment_model.objects.bulk_create([
        treatment_model(owner=user, name=name, category=category, renewal_days=days, notes=notes)
        for name, category, days, notes in DEFAULT_CARE_TREATMENTS
        if name.lower() not in existing
    ])
