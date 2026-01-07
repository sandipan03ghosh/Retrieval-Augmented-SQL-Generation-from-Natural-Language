from rest_framework import serializers
from .models import ClientDatabase, TableMetadata, ColumnMetadata, RelationshipMetadata

class ClientDatabaseSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = ClientDatabase
        fields = [
            'id', 'name', 'description', 'owner', 'database_type', 
            'host', 'port', 'database_name', 'username', 'password',
            'ssl_enabled', 'ssl_ca', 'ssl_cert', 'ssl_key', 
            'created_at', 'updated_at', 'last_metadata_update', 
            'connection_status'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_metadata_update', 'connection_status']
        extra_kwargs = {
            'password': {'write_only': True}
        }

class QueryExecutionSerializer(serializers.Serializer):
    query = serializers.CharField(required=True)
    params = serializers.JSONField(required=False, allow_null=True)

class ConnectionTestSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()

class QueryResultSerializer(serializers.Serializer):
    columns = serializers.ListField(child=serializers.CharField())
    rows = serializers.ListField()
    status = serializers.CharField()
    success = serializers.BooleanField()