from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.utils import build_error_response, build_success_response
from .models import Conversation, Message
from .serializers import MessageSerializer, serialize_user

User = get_user_model()

DEFAULT_PAGE = 50
MAX_PAGE = 100


def _preview(message):
    if message is None:
        return None
    return {
        'id': message.id,
        'sender': message.sender_id,
        'content': message.content,
        'has_image': bool(message.image),
        'has_audio': bool(message.audio),
        'audio_duration_ms': message.audio_duration_ms,
        'created_at': message.created_at,
    }


def serialize_conversation(conversation, me, request, unread=0, last_message=None):
    return {
        'id': conversation.id,
        'other_user': serialize_user(conversation.other_user(me), request),
        'last_message': _preview(last_message),
        'unread_count': unread,
        'updated_at': conversation.updated_at,
    }


@extend_schema(tags=['Messagerie privée'])
class ConversationViewSet(viewsets.ViewSet):
    """
    Messagerie privée entre éleveurs : une conversation par paire d'utilisateurs,
    messages texte et photo, compteur de non-lus et accusés de lecture.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _conversation(self, request, pk):
        conversation = get_object_or_404(
            Conversation.objects.select_related('user_a', 'user_b'),
            Q(user_a=request.user) | Q(user_b=request.user),
            pk=pk,
        )
        return conversation

    def list(self, request):
        """Mes conversations, la plus récente d'abord, avec dernier message et non-lus."""
        me = request.user
        conversations = list(
            Conversation.objects.filter(Q(user_a=me) | Q(user_b=me))
            .select_related('user_a', 'user_b')
            .annotate(unread=Count(
                'messages',
                filter=Q(messages__read_at__isnull=True) & ~Q(messages__sender=me),
            ))
            .order_by('-updated_at')
        )
        last_ids = (
            Message.objects.filter(conversation__in=conversations)
            .values('conversation').annotate(last_id=Max('id')).values_list('last_id', flat=True)
        )
        last_by_conv = {m.conversation_id: m for m in Message.objects.filter(id__in=list(last_ids))}
        # Une discussion sans aucun message n'est pas affichée dans la liste
        data = [
            serialize_conversation(c, me, request, unread=c.unread, last_message=last_by_conv[c.id])
            for c in conversations if c.id in last_by_conv
        ]
        return Response(build_success_response(
            data=data, message_code='conversations-loaded', message_default='Discussions chargées'
        ))

    def create(self, request):
        """Ouvre (ou retrouve) la discussion avec l'utilisateur `user`."""
        other_id = request.data.get('user')
        try:
            other = User.objects.get(pk=int(other_id))
        except (TypeError, ValueError, User.DoesNotExist):
            return Response(build_error_response(
                message_default='Éleveur introuvable', errors={'user': 'Utilisateur inconnu.'}
            ), status=status.HTTP_404_NOT_FOUND)
        if other.pk == request.user.pk:
            return Response(build_error_response(
                message_default='Action impossible', errors={'user': 'Vous ne pouvez pas vous écrire à vous-même.'}
            ), status=status.HTTP_400_BAD_REQUEST)

        conversation, created = Conversation.between(request.user, other)
        return Response(build_success_response(
            data=serialize_conversation(conversation, request.user, request),
            message_code='conversation-ready',
            message_default='Discussion prête',
        ), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        """
        GET : derniers messages (`limit`, défaut 50). `after_id` renvoie uniquement les plus récents
        (pour l'actualisation), `before_id` les plus anciens (pour remonter l'historique).
        Lire une discussion marque comme lus les messages reçus.
        POST : envoie un message (`content` et/ou `image`).
        """
        conversation = self._conversation(request, pk)
        me = request.user

        if request.method == 'POST':
            serializer = MessageSerializer(data=request.data, context={'request': request})
            if not serializer.is_valid():
                return Response(build_error_response(
                    message_default="Le message n'a pas pu être envoyé", errors=serializer.errors
                ), status=status.HTTP_400_BAD_REQUEST)
            message = serializer.save(conversation=conversation, sender=me)
            conversation.updated_at = message.created_at
            conversation.save(update_fields=['updated_at'])
            return Response(build_success_response(
                data=MessageSerializer(message, context={'request': request}).data,
                message_code='message-sent', message_default='Message envoyé',
            ), status=status.HTTP_201_CREATED)

        try:
            limit = max(1, min(int(request.query_params.get('limit', DEFAULT_PAGE)), MAX_PAGE))
            after_id = request.query_params.get('after_id')
            before_id = request.query_params.get('before_id')
            after_id = int(after_id) if after_id else None
            before_id = int(before_id) if before_id else None
        except ValueError:
            return Response(build_error_response(
                message_default='Paramètres invalides'
            ), status=status.HTTP_400_BAD_REQUEST)

        qs = conversation.messages.all()
        if after_id is not None:
            batch = list(qs.filter(id__gt=after_id).order_by('id')[:limit])
            has_more = False
        else:
            if before_id is not None:
                qs = qs.filter(id__lt=before_id)
            batch = list(qs.order_by('-id')[:limit])[::-1]
            has_more = bool(batch) and conversation.messages.filter(id__lt=batch[0].id).exists()

        # Lire la discussion = marquer les messages reçus comme lus
        conversation.messages.filter(read_at__isnull=True).exclude(sender=me).update(read_at=timezone.now())

        last_read = (
            conversation.messages.filter(sender=me, read_at__isnull=False)
            .order_by('-id').values_list('id', flat=True).first()
        )
        return Response(build_success_response(
            data={
                'messages': MessageSerializer(batch, many=True, context={'request': request}).data,
                'has_more': has_more,
                # Tous mes messages jusqu'à cet identifiant ont été lus par l'autre personne
                'my_read_up_to': last_read,
                'other_user': serialize_user(conversation.other_user(me), request),
            },
            message_code='messages-loaded', message_default='Messages chargés',
        ))

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        """Nombre total de messages non lus (pastille de la messagerie)."""
        me = request.user
        unread = (
            Message.objects.filter(
                Q(conversation__user_a=me) | Q(conversation__user_b=me), read_at__isnull=True
            ).exclude(sender=me).count()
        )
        return Response(build_success_response(
            data={'unread': unread}, message_code='unread-count', message_default='Messages non lus'
        ))

    @action(detail=False, methods=['get'])
    def users(self, request):
        """Recherche d'éleveurs pour démarrer une discussion (`search`, 30 résultats maximum)."""
        term = (request.query_params.get('search') or '').strip()
        qs = User.objects.exclude(pk=request.user.pk).filter(is_active=True)
        if term:
            qs = qs.filter(
                Q(farm_name__icontains=term) | Q(first_name__icontains=term)
                | Q(last_name__icontains=term) | Q(username__icontains=term)
                | Q(location__icontains=term)
            )
        qs = qs.order_by('farm_name', 'first_name', 'id')[:30]
        return Response(build_success_response(
            data=[serialize_user(u, request) for u in qs],
            message_code='users-loaded', message_default='Éleveurs trouvés',
        ))
