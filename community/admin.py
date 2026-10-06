from django.contrib import admin

from .models import Comment, CommentReaction, MarketplaceListing, Post, PostLike, PostMedia


class PostMediaInline(admin.TabularInline):
    model = PostMedia
    extra = 0


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'title', 'created_at', 'updated_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'content', 'tags', 'author__username')
    inlines = [PostMediaInline]


@admin.register(PostMedia)
class PostMediaAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'media_type', 'position', 'created_at')
    list_filter = ('media_type',)
    search_fields = ('post__title',)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'author', 'parent', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('content', 'author__username', 'post__title')


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'user', 'emoji', 'created_at')
    list_filter = ('emoji',)
    search_fields = ('post__title', 'user__username')


@admin.register(CommentReaction)
class CommentReactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'comment', 'user', 'emoji', 'created_at')
    list_filter = ('emoji',)
    search_fields = ('comment__content', 'user__username')


@admin.register(MarketplaceListing)
class MarketplaceListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'seller', 'listing_type', 'status', 'price', 'created_at')
    list_filter = ('listing_type', 'status')
    search_fields = ('title', 'description', 'location', 'seller__username')
