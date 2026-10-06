from django.contrib import admin

from .models import Conversation, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_a', 'user_b', 'created_at', 'updated_at')
    search_fields = ('user_a__username', 'user_b__username')
    date_hierarchy = 'updated_at'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'created_at', 'read_at')
    list_filter = ('read_at',)
    search_fields = ('content', 'sender__username')
    date_hierarchy = 'created_at'
