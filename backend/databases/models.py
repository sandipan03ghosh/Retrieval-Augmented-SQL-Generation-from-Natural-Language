from django.db import models
from django.conf import settings

# Database type constants
DATABASE_TYPES = [
    ('postgresql', 'PostgreSQL'),
]

# Connection status constants
CONNECTION_STATUS = [
    ('connected', 'Connected'),
    ('disconnected', 'Disconnected'),
    ('error', 'Error'),
]

class ClientDatabase(models.Model):
    """Represents a client's database connection"""
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='databases')
    database_type = models.CharField(max_length=50, choices=DATABASE_TYPES, default='postgresql')
    host = models.CharField(max_length=255)
    port = models.IntegerField(default=5432)
    database_name = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    # Password should be encrypted in actual implementation
    password = models.CharField(max_length=255)
    ssl_enabled = models.BooleanField(default=False)
    ssl_ca = models.TextField(null=True, blank=True)
    ssl_cert = models.TextField(null=True, blank=True)
    ssl_key = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_metadata_update = models.DateTimeField(null=True, blank=True)
    connection_status = models.CharField(max_length=20, choices=CONNECTION_STATUS, default='disconnected')
    
    def __str__(self):
        return f"{self.name} ({self.database_type})"

class TableMetadata(models.Model):
    """Stores metadata about database tables"""
    database = models.ForeignKey(ClientDatabase, on_delete=models.CASCADE, related_name='tables')
    schema_name = models.CharField(max_length=255, default='public')
    table_name = models.CharField(max_length=255)
    table_type = models.CharField(max_length=50)  # table, view, etc.
    description = models.TextField(null=True, blank=True)
    row_count = models.IntegerField(null=True, blank=True)
    embedding_vector = models.JSONField(null=True, blank=True)  # For semantic search
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('database', 'schema_name', 'table_name')
    
    def __str__(self):
        return f"{self.schema_name}.{self.table_name}"

class ColumnMetadata(models.Model):
    """Stores metadata about table columns"""
    table = models.ForeignKey(TableMetadata, on_delete=models.CASCADE, related_name='columns')
    column_name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=100)
    is_nullable = models.BooleanField(default=True)
    is_primary_key = models.BooleanField(default=False)
    is_foreign_key = models.BooleanField(default=False)
    description = models.TextField(null=True, blank=True)
    embedding_vector = models.JSONField(null=True, blank=True)  # For semantic search
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('table', 'column_name')
    
    def __str__(self):
        return f"{self.table.table_name}.{self.column_name}"

class RelationshipMetadata(models.Model):
    """Stores relationships between tables (foreign keys)"""
    from_column = models.ForeignKey(ColumnMetadata, on_delete=models.CASCADE, related_name='outgoing_relationships')
    to_column = models.ForeignKey(ColumnMetadata, on_delete=models.CASCADE, related_name='incoming_relationships')
    relationship_type = models.CharField(max_length=50)  # one-to-one, one-to-many, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.from_column} -> {self.to_column}"

class ERDiagram(models.Model):
    """Stores ER diagram representation of a database schema"""
    database = models.OneToOneField(ClientDatabase, on_delete=models.CASCADE, related_name='er_diagram')
    diagram_data = models.JSONField(help_text="JSON representation of the ER diagram")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"ER Diagram for {self.database.name}"
