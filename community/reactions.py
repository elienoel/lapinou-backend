from collections import Counter


def set_reaction(model, target_field, target, user, emoji):
    """
    Applique la réaction `emoji` de `user` sur `target` (publication ou commentaire) :
    - aucune réaction existante  -> création
    - même emoji                 -> retrait (bascule)
    - emoji différent            -> remplacement
    Renvoie l'emoji actif après l'opération, ou None s'il a été retiré.
    """
    existing = model.objects.filter(**{target_field: target, 'user': user}).first()
    if existing:
        if existing.emoji == emoji:
            existing.delete()
            return None
        existing.emoji = emoji
        existing.save(update_fields=['emoji'])
        return emoji
    model.objects.create(**{target_field: target, 'user': user, 'emoji': emoji})
    return emoji


def summarize(reactions, user=None):
    """
    Résume un ensemble de réactions (utilise le cache de prefetch si présent).
    Renvoie (liste [{'emoji', 'count'}] triée par fréquence, réaction de `user` ou None).
    """
    reactions = list(reactions)
    counts = Counter(r.emoji for r in reactions)
    summary = [{'emoji': e, 'count': c} for e, c in counts.most_common()]
    mine = None
    if user is not None and getattr(user, 'is_authenticated', False):
        mine = next((r.emoji for r in reactions if r.user_id == user.id), None)
    return summary, mine
