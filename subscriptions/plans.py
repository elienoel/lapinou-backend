"""
Paliers d'abonnement : le prix dépend du nombre de fiches lapins de l'élevage.
Gratuit sous 5 lapins, Éleveur de 5 à 10, Pro au-delà (prix mensuels en F CFA).
"""
from dataclasses import dataclass

FREE = 'free'
BREEDER = 'breeder'
PRO = 'pro'

# Durée achetée par un paiement
PERIOD_DAYS = 30


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    price: int
    # Nombre maximum de fiches lapins ; None = illimité
    max_rabbits: int | None

    def allows(self, count):
        return self.max_rabbits is None or count <= self.max_rabbits

    def as_dict(self):
        return {
            'code': self.code, 'name': self.name, 'price': self.price,
            'max_rabbits': self.max_rabbits, 'period_days': PERIOD_DAYS,
        }


PLANS = {
    FREE: Plan(FREE, 'Gratuit', 0, 4),
    BREEDER: Plan(BREEDER, 'Éleveur', 1200, 10),
    PRO: Plan(PRO, 'Pro', 2500, None),
}

# Ordre croissant, pour trouver le palier minimum
ORDER = [FREE, BREEDER, PRO]

CHOICES = [(code, PLANS[code].name) for code in ORDER]
PAID_CHOICES = [(code, PLANS[code].name) for code in ORDER if PLANS[code].price > 0]


def plan_for_rabbits(count):
    """Palier minimum qui couvre `count` fiches lapins."""
    for code in ORDER:
        if PLANS[code].allows(count):
            return PLANS[code]
    return PLANS[PRO]
