from django.db import transaction
from rest_framework import permissions, serializers as drf_serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from core.utils import CustomViewSet, build_success_response, build_error_response
from .media_validation import classify_and_validate
from .models import (
    Post, PostMedia, Comment, CommentReaction, MarketplaceListing, PostLike,
    REACTION_EMOJIS, DEFAULT_REACTION,
)
from .reactions import set_reaction, summarize
from .serializers import (
    PostSerializer,
    CommentSerializer,
    MarketplaceListingSerializer,
)


class OwnerOnlyWriteMixin:
    """
    Pour les ressources visibles par tous : seul le propriétaire (`owner_field`)
    peut modifier ou supprimer un objet.
    """
    owner_field = 'author'

    def _forbid_if_not_owner(self, request, pk):
        obj = self.get_object(pk=pk)
        if getattr(obj, f'{self.owner_field}_id') != request.user.id:
            return obj, Response(build_error_response(
                message_default="Vous ne pouvez modifier que vos propres contenus.",
                errors={'permission': "Action réservée à l'auteur."}
            ), status=status.HTTP_403_FORBIDDEN)
        return obj, None

    def update(self, request, pk=None, *args, **kwargs):
        _, forbidden = self._forbid_if_not_owner(request, pk)
        if forbidden:
            return forbidden
        return super().update(request, pk=pk, *args, **kwargs)

    def destroy(self, request, pk=None):
        obj, forbidden = self._forbid_if_not_owner(request, pk)
        if forbidden:
            return forbidden
        self.before_destroy(obj)
        return super().destroy(request, pk=pk)

    def before_destroy(self, obj):
        pass


@extend_schema(tags=['Communauté & Fil d\'actualité'])
class PostViewSet(OwnerOnlyWriteMixin, CustomViewSet):
    """
    ViewSet pour les publications de la communauté d'éleveurs.
    Lecture libre pour tous, création / modification réservée aux membres connectés.
    """
    queryset = Post.objects.all().select_related('author').prefetch_related('comments', 'media', 'likes')
    serializer_class = PostSerializer
    user_field_lookup = None  # La communauté est publique en lecture pour tous

    filterset_fields = {
        'author': ['exact'],
        'tags': ['icontains'],
    }
    search_fields = ['title', 'content', 'tags', 'author__username', 'author__farm_name']
    export_columns = [
        ('ID', ['id']),
        ('Titre', ['title']),
        ('Auteur', ['author_name']),
        ('Date', ['created_at']),
        ('Commentaires', ['comments_count']),
    ]
    export_filename = "publications_communaute.xlsx"

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'comments']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def create(self, request):
        """
        Crée une publication : texte et/ou photos/vidéos (champ multipart `media`, répétable).
        """
        serializer = self.serializer_class(
            data=request.data,
            context={'request': request, 'extra_args': {'user': request.user}}
        )
        if not serializer.is_valid():
            return Response(build_error_response(
                message_default='Erreur de publication',
                errors=serializer.errors
            ), status=status.HTTP_400_BAD_REQUEST)

        try:
            media_files = classify_and_validate(request.FILES.getlist('media'))
        except drf_serializers.ValidationError as e:
            return Response(build_error_response(
                message_default='Erreur de publication',
                errors=e.detail
            ), status=status.HTTP_400_BAD_REQUEST)

        content = (serializer.validated_data.get('content') or '').strip()
        if not content and not media_files:
            return Response(build_error_response(
                message_default='Erreur de publication',
                errors={'content': 'Écrivez un message ou ajoutez une photo/vidéo.'}
            ), status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            post = serializer.save(author=request.user)
            for position, (f, media_type) in enumerate(media_files):
                PostMedia.objects.create(post=post, file=f, media_type=media_type, position=position)

        post = self.get_queryset().get(pk=post.pk)
        return Response(build_success_response(
            data=self.serializer_class(post, context={'request': request}).data,
            message_code='data-saved',
            message_default='Publication partagée avec succès'
        ), status=status.HTTP_201_CREATED)

    def before_destroy(self, post):
        # Supprimer aussi les fichiers du stockage
        for m in post.media.all():
            m.file.delete(save=False)

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        """
        GET: Récupère les commentaires d'un post.
        POST: Ajoute un commentaire sous ce post.
        """
        post = self.get_object(pk=pk)

        if request.method == 'GET':
            comments = post.comments.all().select_related('author').prefetch_related('reactions')
            serializer = CommentSerializer(comments, many=True, context={'request': request})
            return Response(build_success_response(
                data=serializer.data,
                message_code='comments-loaded',
                message_default='Commentaires chargés avec succès'
            ))

        # POST: ajouter un commentaire
        if not request.user.is_authenticated:
            return Response(build_error_response(
                message_default='Authentification requise pour commenter',
                errors={'not-auth': 'Authentification requise.'}
            ), status=status.HTTP_401_UNAUTHORIZED)

        serializer = CommentSerializer(
            data=request.data,
            context={'request': request, 'extra_args': {'user': request.user}}
        )
        if serializer.is_valid():
            parent = serializer.validated_data.get('parent')
            if parent is not None:
                if parent.post_id != post.id:
                    return Response(build_error_response(
                        message_default='Erreur de validation',
                        errors={'parent': "Ce commentaire n'appartient pas à cette publication."}
                    ), status=status.HTTP_400_BAD_REQUEST)
                # Un seul niveau de réponses : répondre à une réponse rattache au commentaire racine
                parent = parent.parent or parent
            serializer.save(post=post, author=request.user, parent=parent)
            return Response(build_success_response(
                data=serializer.data,
                message_code='data-saved',
                message_default='Commentaire ajouté avec succès'
            ), status=status.HTTP_201_CREATED)

        return Response(build_error_response(
            message_default='Erreur de validation',
            errors=serializer.errors
        ), status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        """
        Réagit à une publication avec un emoji (`emoji` dans le corps, ❤️ par défaut).
        Même emoji que la réaction actuelle = retrait, autre emoji = remplacement.
        """
        if not request.user.is_authenticated:
            return Response(build_error_response(
                message_default='Authentification requise pour réagir à une publication',
                errors={'not-auth': 'Authentification requise.'}
            ), status=status.HTTP_401_UNAUTHORIZED)

        emoji = request.data.get('emoji') or DEFAULT_REACTION
        if emoji not in REACTION_EMOJIS:
            return Response(build_error_response(
                message_default='Réaction non autorisée',
                errors={'emoji': f'Choisissez parmi : {" ".join(REACTION_EMOJIS)}'}
            ), status=status.HTTP_400_BAD_REQUEST)

        post = self.get_object(pk=pk)
        my_reaction = set_reaction(PostLike, 'post', post, request.user, emoji)
        reactions, _ = summarize(PostLike.objects.filter(post=post))

        return Response(build_success_response(
            data={
                'is_liked': my_reaction is not None,
                'my_reaction': my_reaction,
                'reactions': reactions,
                'likes_count': sum(r['count'] for r in reactions),
            },
            message_code='like-toggled',
            message_default='Réaction mise à jour'
        ))


@extend_schema(tags=['Communauté & Fil d\'actualité'])
class CommentViewSet(OwnerOnlyWriteMixin, CustomViewSet):
    """
    ViewSet pour les commentaires : lecture libre, modification / suppression réservées
    à leur auteur, réactions emoji ouvertes à tout membre connecté.
    """
    queryset = Comment.objects.all().select_related('author', 'post').prefetch_related('reactions')
    serializer_class = CommentSerializer
    user_field_lookup = None  # Visibles par tous ; l'écriture est limitée à l'auteur
    owner_field = 'author'

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def react(self, request, pk=None):
        """
        Réagit à un commentaire avec un emoji (`emoji` dans le corps, ❤️ par défaut).
        Même emoji = retrait, autre emoji = remplacement.
        """
        emoji = request.data.get('emoji') or DEFAULT_REACTION
        if emoji not in REACTION_EMOJIS:
            return Response(build_error_response(
                message_default='Réaction non autorisée',
                errors={'emoji': f'Choisissez parmi : {" ".join(REACTION_EMOJIS)}'}
            ), status=status.HTTP_400_BAD_REQUEST)

        comment = self.get_object(pk=pk)
        my_reaction = set_reaction(CommentReaction, 'comment', comment, request.user, emoji)
        reactions, _ = summarize(CommentReaction.objects.filter(comment=comment))

        return Response(build_success_response(
            data={
                'my_reaction': my_reaction,
                'reactions': reactions,
                'likes_count': sum(r['count'] for r in reactions),
            },
            message_code='reaction-updated',
            message_default='Réaction mise à jour'
        ))


@extend_schema(tags=['Communauté & Fil d\'actualité'])
class MarketplaceListingViewSet(OwnerOnlyWriteMixin, CustomViewSet):
    """
    ViewSet pour les petites annonces d'élevage : vente reproducteurs, matériel, etc.
    """
    queryset = MarketplaceListing.objects.all().select_related('seller')
    serializer_class = MarketplaceListingSerializer
    user_field_lookup = None  # Les annonces sont visibles par tout le monde
    owner_field = 'seller'

    filterset_fields = {
        'listing_type': ['exact'],
        'status': ['exact'],
        'location': ['exact', 'icontains'],
        'seller': ['exact'],
    }
    search_fields = ['title', 'description', 'location', 'seller__farm_name']
    export_columns = [
        ('ID', ['id']),
        ('Titre', ['title']),
        ('Type', ['listing_type_display']),
        ('Prix', ['price']),
        ('Vendeur', ['seller_name']),
        ('Téléphone', ['seller_phone']),
        ('Statut', ['status_display']),
        ('Lieu', ['location']),
    ]
    export_filename = "annonces_marketplace.xlsx"

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def create(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={'request': request, 'extra_args': {'user': request.user}}
        )
        if serializer.is_valid():
            serializer.save(seller=request.user)
            return Response(build_success_response(
                data=serializer.data,
                message_code='data-saved',
                message_default='Annonce créée avec succès'
            ), status=status.HTTP_201_CREATED)
        return Response(build_error_response(
            message_default='Erreur de validation',
            errors=serializer.errors
        ), status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def my_listings(self, request):
        """
        Retourne uniquement les annonces publiées par l'éleveur connecté.
        """
        if not request.user.is_authenticated:
            return Response(build_error_response(
                message_default='Authentification requise',
                errors={'not-auth': 'Authentification requise.'}
            ), status=status.HTTP_401_UNAUTHORIZED)

        qs = self.get_queryset().filter(seller=request.user)
        serializer = self.get_serializer(qs, many=True)
        return Response(build_success_response(
            data=serializer.data,
            message_code='my-listings',
            message_default='Vos annonces'
        ))
