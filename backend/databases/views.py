from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import ClientDatabase, TableMetadata, ColumnMetadata, RelationshipMetadata
from .serializers import (
    ClientDatabaseSerializer,
    QueryExecutionSerializer,
    ConnectionTestSerializer,
    QueryResultSerializer
)
from .services import DatabaseConnector, MetadataExtractor, MetadataVectorizer

class DatabaseViewSet(viewsets.ModelViewSet):
    """CRUD operations for database connections"""
    queryset = ClientDatabase.objects.all()
    serializer_class = ClientDatabaseSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Override get_queryset to ensure users can only access their own databases
        """
        return ClientDatabase.objects.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test database connection"""
        database = self.get_object()
        connector = DatabaseConnector()
        success, message = connector.test_connection(database)
        
        serializer = ConnectionTestSerializer(data={
            'success': success,
            'message': message
        })
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def execute_query(self, request, pk=None):
        """Execute SQL query on the database"""
        database = self.get_object()
        query_serializer = QueryExecutionSerializer(data=request.data)
        query_serializer.is_valid(raise_exception=True)
        
        connector = DatabaseConnector()
        result = connector.execute_query(
            database,
            query_serializer.validated_data['query'],
            query_serializer.validated_data.get('params')
        )
        
        # Ensure that error_type is included in the response
        if not result.get("success", True):
            if "error_type" not in result:
                # Set a default error type if none is provided by the connector
                result["error_type"] = "execution_error"
                
        result_serializer = QueryResultSerializer(data=result)
        result_serializer.is_valid(raise_exception=True)
        return Response(result_serializer.data)
    
    @action(detail=True, methods=['post'])
    def extract_metadata(self, request, pk=None):
        """Extract schema metadata from the database"""
        database = self.get_object()
        extractor = MetadataExtractor()
        success, message, changes = extractor.extract_full_metadata(database)
        
        # Generate ER diagram after metadata extraction
        if success:
            from .services import generate_er_diagram
            generate_er_diagram(database.id)
        
        return Response({
            'success': success,
            'message': message,
            'changes': changes
        })
    
    @action(detail=True, methods=['post'])
    def update_embeddings(self, request, pk=None):
        """Update embeddings for database metadata"""
        database = self.get_object()
        vectorizer = MetadataVectorizer()
        success, message = vectorizer.update_all_embeddings(database)
        
        return Response({
            'success': success,
            'message': message
        })
    
    @action(detail=True, methods=['get'])
    def schema(self, request, pk=None):
        """Get full schema for a database"""
        database = self.get_object()
        
        # Get tables for this database
        tables = TableMetadata.objects.filter(database=database)
        
        # Build the schema response
        schema_data = []
        
        for table in tables:
            # Get columns for this table
            columns = ColumnMetadata.objects.filter(table=table)
            column_data = []
            
            for column in columns:
                column_data.append({
                    'id': column.id,
                    'name': column.column_name,
                    'data_type': column.data_type,
                    'is_nullable': column.is_nullable,
                    'is_primary_key': column.is_primary_key,
                    'is_foreign_key': column.is_foreign_key,
                    'description': column.description
                })
            
            # Add table with its columns to schema
            schema_data.append({
                'id': table.id,
                'schema_name': table.schema_name,
                'table_name': table.table_name,
                'table_type': table.table_type,
                'description': table.description,
                'row_count': table.row_count,
                'columns': column_data
            })
        
        return Response(schema_data)
    
    @action(detail=True, methods=['get'])
    def relationships(self, request, pk=None):
        """Get relationships between tables in this database"""
        database = self.get_object()
        
        # Get all tables for this database
        tables = TableMetadata.objects.filter(database=database)
        table_ids = [table.id for table in tables]
        
        # Get all columns for these tables
        columns = ColumnMetadata.objects.filter(table__in=tables)
        column_ids = [column.id for column in columns]
        
        # Get relationships where both columns are from this database
        relationships = RelationshipMetadata.objects.filter(
            from_column__in=column_ids,
            to_column__in=column_ids
        )
        
        # Build relationship data
        relationship_data = []
        
        for rel in relationships:
            relationship_data.append({
                'id': rel.id,
                'from_schema': rel.from_column.table.schema_name,
                'from_table': rel.from_column.table.table_name,
                'from_column': rel.from_column.column_name,
                'to_schema': rel.to_column.table.schema_name,
                'to_table': rel.to_column.table.table_name,
                'to_column': rel.to_column.column_name,
                'relationship_type': rel.relationship_type
            })
        
        return Response(relationship_data)
    
    @action(detail=True, methods=['get'])
    def search(self, request, pk=None):
        """Search database schema metadata"""
        database = self.get_object()
        query = request.query_params.get('q', '')
        
        if not query:
            return Response({'error': 'Query parameter "q" is required'}, status=400)
        
        vectorizer = MetadataVectorizer()
        results = vectorizer.search_metadata(database, query)

        return Response(results)
    
    @action(detail=True, methods=['post'])
    def update_description(self, request, pk=None):
        """Update description for table or column metadata"""
        database = self.get_object()
        
        # Validate input
        if 'type' not in request.data or 'id' not in request.data or 'description' not in request.data:
            return Response({
                'success': False,
                'message': 'type, id, and description are required'
            }, status=400)
        
        metadata_type = request.data['type']
        metadata_id = request.data['id']
        description = request.data['description']
        
        try:
            if metadata_type == 'table':
                table = TableMetadata.objects.get(id=metadata_id, database=database)
                table.description = description
                table.save(update_fields=['description'])
            elif metadata_type == 'column':
                # Ensure column belongs to this database
                column = ColumnMetadata.objects.get(id=metadata_id, table__database=database)
                column.description = description
                column.save(update_fields=['description'])
            else:
                return Response({
                    'success': False,
                    'message': f'Invalid metadata type: {metadata_type}'
                }, status=400)
                
            return Response({
                'success': True,
                'message': 'Description updated successfully'
            })
            
        except (TableMetadata.DoesNotExist, ColumnMetadata.DoesNotExist):
            return Response({
                'success': False,
                'message': f'{metadata_type} with id {metadata_id} not found'
            }, status=404)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=500)
            
    @action(detail=True, methods=['post'])
    def generate_description(self, request, pk=None):
        """Generate AI description for table or column metadata"""
        database = self.get_object()
        
        # Add detailed logging
        import logging
        logging.info(f"generate_description called with database_id={pk}, data={request.data}")
        
        # Validate input
        if 'type' not in request.data or 'id' not in request.data:
            return Response({
                'success': False,
                'message': 'type and id are required'
            }, status=400)
        
        metadata_type = request.data['type']
        metadata_id = request.data['id']
        
        logging.info(f"Generating description for {metadata_type} with id {metadata_id}")
        
        try:
            from llm_agent.services import get_metadata_description
            connector = DatabaseConnector()
            
            # Prepare context data for AI
            context = {}
            name = ""
            
            if metadata_type == 'table':
                # Get table metadata
                table = TableMetadata.objects.get(id=metadata_id, database=database)
                name = table.table_name
                context = {
                    'schema': table.schema_name,
                    'table_type': table.table_type,
                    'row_count': table.row_count
                }
                
                # Add some column information for context
                columns = ColumnMetadata.objects.filter(table=table)
                context['columns'] = [
                    {
                        'name': col.column_name,
                        'type': col.data_type,
                        'primary_key': col.is_primary_key, 
                        'foreign_key': col.is_foreign_key
                    } 
                    for col in columns[:10]  # Limit to first 10 columns
                ]
                
                logging.info(f"Table context: {context}")
                
            elif metadata_type == 'column':
                # Get column metadata
                column = ColumnMetadata.objects.get(id=metadata_id, table__database=database)
                name = column.column_name
                table = column.table
                
                # Basic column context
                context = {
                    'schema': table.schema_name,
                    'table': table.table_name,
                    'data_type': column.data_type,
                    'nullable': column.is_nullable,
                    'primary_key': column.is_primary_key,
                    'foreign_key': column.is_foreign_key,
                }
                
                logging.info(f"Column context before sample values: {context}")
                
                # Get sample distinct values to provide better context for AI
                try:
                    sample_values = connector.get_column_sample_values(
                        database, 
                        table.schema_name, 
                        table.table_name, 
                        column.column_name, 
                        limit=10
                    )
                    
                    if sample_values:
                        context['sample_values'] = sample_values
                        logging.info(f"Sample values retrieved: {sample_values[:5]}...")
                    else:
                        logging.warning("No sample values retrieved")
                except Exception as sample_err:
                    logging.error(f"Error retrieving sample values: {str(sample_err)}")
                    # Continue without sample values
            else:
                return Response({
                    'success': False,
                    'message': f'Invalid metadata type: {metadata_type}'
                }, status=400)
            
            # Generate description using LLM
            logging.info(f"Calling get_metadata_description with type={metadata_type}, name={name}")
            # Pass the request.user to track token usage
            description = get_metadata_description(metadata_type, name, context, user=request.user)
            logging.info(f"Description generated: {description[:100]}...")
            
            return Response({
                'success': True,
                'description': description,
                'context': context  # Include context data in response
            })
            
        except (TableMetadata.DoesNotExist, ColumnMetadata.DoesNotExist) as e:
            logging.error(f"Metadata not found: {str(e)}")
            return Response({
                'success': False,
                'message': f'{metadata_type} with id {metadata_id} not found'
            }, status=404)
            
        except Exception as e:
            logging.exception(f"Error in generate_description: {str(e)}")
            return Response({
                'success': False,
                'message': f"Error generating description: {str(e)}"
            }, status=500)
    
    @action(detail=True, methods=['get'])
    def er_diagram(self, request, pk=None):
        """Get or generate ER diagram for a database"""
        database = self.get_object()
        
        from .services import generate_er_diagram
        from .models import ERDiagram
        
        # Try to get an existing diagram
        try:
            diagram = ERDiagram.objects.get(database=database)
            return Response(diagram.diagram_data)
        except ERDiagram.DoesNotExist:
            # Generate new diagram if it doesn't exist
            result = generate_er_diagram(database.id)
            
            if result["success"]:
                return Response(result["diagram_data"])
            else:
                return Response({"error": result["error"]}, status=status.HTTP_400_BAD_REQUEST)
