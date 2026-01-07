from rest_framework import serializers
from .models import Session, Query

class QuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Query
        fields = ['id', 'prompt', 'response', 'created_at', 'success', 'error_type', 'error', 'generated_sql', 'explanation']


class SessionSerializer(serializers.ModelSerializer):
    queries = QuerySerializer(many=True, read_only=True)
    query_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Session
        fields = ['id', 'title', 'database_name', 'database_id', 'created_at', 'updated_at', 'queries', 'query_count']
        
    def get_query_count(self, obj):
        return obj.queries.count()


class SessionListSerializer(serializers.ModelSerializer):
    query_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Session
        fields = ['id', 'title', 'database_name', 'database_id', 'created_at', 'updated_at', 'query_count']
        
    def get_query_count(self, obj):
        return obj.queries.count()
