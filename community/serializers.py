from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Post, PostMedia, Comment, MarketplaceListing
from .reactions import summarize
from core.utils import UserActionMixinSerializer


class CommentSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les commentaires d'une publication (et leurs réponses via `parent`).
    """
    author_name = serializers.SerializerMethodField()
    author_avatar = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()
    my_reaction = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id', 'post', 'parent', 'author', 'author_name', 'author_avatar',
            'content', 'reactions', 'my_reaction', 'likes_count',
            'created_at', 'updated_at', 'created_by_user'
        ]
        read_only_fields = ['id', 'post', 'author', 'created_at', 'updated_at', 'created_by_user']

    @extend_schema_field(serializers.CharField())
    def get_author_name(self, obj):
        if obj.author:
            return obj.author.farm_name or obj.author.get_full_name() or obj.author.username
        return ""

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_author_avatar(self, obj):
        if obj.author and obj.author.avatar:
            return obj.author.avatar.url
        return None

    def _summary(self, obj):
        request = self.context.get('request')
        return summarize(obj.reactions.all(), getattr(request, 'user', None))

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_reactions(self, obj):
        return self._summary(obj)[0]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_my_reaction(self, obj):
        return self._summary(obj)[1]

    @extend_schema_field(serializers.IntegerField())
    def get_likes_count(self, obj):
        return sum(r['count'] for r in self._summary(obj)[0])


class PostMediaSerializer(serializers.ModelSerializer):
    """
    Photo ou vidéo attachée à une publication.
    """
    url = serializers.SerializerMethodField()

    class Meta:
        model = PostMedia
        fields = ['id', 'media_type', 'url', 'position']
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_url(self, obj):
        request = self.context.get('request')
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class PostSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les publications de la communauté d'éleveurs.
    """
    author_name = serializers.SerializerMethodField()
    author_farm = serializers.CharField(source='author.farm_name', read_only=True)
    author_avatar = serializers.SerializerMethodField()
    comments_count = serializers.IntegerField(source='comments.count', read_only=True)
    likes_count = serializers.IntegerField(source='likes.count', read_only=True)
    is_liked = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()
    my_reaction = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id', 'author', 'author_name', 'author_farm', 'author_avatar',
            'title', 'content', 'image', 'media', 'tags', 'comments_count',
            'likes_count', 'is_liked', 'reactions', 'my_reaction',
            'created_at', 'updated_at', 'created_by_user'
        ]
        read_only_fields = [
            'id', 'author', 'image', 'media', 'comments_count', 'likes_count', 'is_liked',
            'reactions', 'my_reaction',
            'created_at', 'updated_at', 'created_by_user'
        ]

    @extend_schema_field(serializers.CharField())
    def get_author_name(self, obj):
        if obj.author:
            return obj.author.farm_name or obj.author.get_full_name() or obj.author.username
        return ""

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_author_avatar(self, obj):
        if obj.author and obj.author.avatar:
            return obj.author.avatar.url
        return None

    @extend_schema_field(PostMediaSerializer(many=True))
    def get_media(self, obj):
        items = PostMediaSerializer(obj.media.all(), many=True, context=self.context).data
        # Publications antérieures : l'ancienne image unique devient le premier média
        if obj.image:
            request = self.context.get('request')
            url = obj.image.url
            legacy = {
                'id': 0,
                'media_type': PostMedia.MediaType.IMAGE,
                'url': request.build_absolute_uri(url) if request else url,
                'position': -1,
            }
            return [legacy, *items]
        return list(items)

    def _summary(self, obj):
        request = self.context.get('request')
        return summarize(obj.likes.all(), getattr(request, 'user', None))

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_reactions(self, obj):
        return self._summary(obj)[0]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_my_reaction(self, obj):
        return self._summary(obj)[1]

    @extend_schema_field(serializers.BooleanField())
    def get_is_liked(self, obj):
        return self._summary(obj)[1] is not None


class MarketplaceListingSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les petites annonces d'élevage.
    """
    seller_name = serializers.SerializerMethodField()
    seller_phone = serializers.CharField(source='seller.phone_number', read_only=True)
    seller_farm = serializers.CharField(source='seller.farm_name', read_only=True)
    listing_type_display = serializers.CharField(source='get_listing_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = MarketplaceListing
        fields = [
            'id', 'seller', 'seller_name', 'seller_phone', 'seller_farm',
            'title', 'listing_type', 'listing_type_display',
            'description', 'price', 'location', 'photo',
            'status', 'status_display',
            'created_at', 'updated_at', 'created_by_user'
        ]
        read_only_fields = ['id', 'seller', 'created_at', 'updated_at', 'created_by_user']

    @extend_schema_field(serializers.CharField())
    def get_seller_name(self, obj):
        if obj.seller:
            return obj.seller.farm_name or obj.seller.get_full_name() or obj.seller.username
        return ""

