import psycopg2
import pytz
from datetime import datetime
from .models import ClientDatabase, TableMetadata, ColumnMetadata, RelationshipMetadata, CONNECTION_STATUS

class DatabaseConnector:
    """Handles database connection and basic operations"""
    
    def create_connection(self, database_obj):
        """Create a connection to the database using stored credentials"""
        try:
            if database_obj.database_type == 'postgresql':
                conn = psycopg2.connect(
                    dbname=database_obj.database_name,
                    user=database_obj.username,
                    password=database_obj.password,
                    host=database_obj.host,
                    port=database_obj.port,
                    connect_timeout=5
                )
                # Update connection status
                database_obj.connection_status = 'connected'
                database_obj.save(update_fields=['connection_status'])
                return conn
            else:
                raise ValueError(f"Unsupported database type: {database_obj.database_type}")
        except Exception as e:
            # Update connection status on error
            database_obj.connection_status = 'error'
            database_obj.save(update_fields=['connection_status'])
            raise e
    
    def test_connection(self, database_obj):
        """Test if the database connection works"""
        try:
            conn = self.create_connection(database_obj)
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
            conn.close()
            database_obj.connection_status = 'disconnected'  # Set to disconnected after successful test
            database_obj.save(update_fields=['connection_status'])
            return True, "Connection successful"
        except Exception as e:
            return False, str(e)
    
    def execute_query(self, database_obj, query, params=None):
        """Execute a SQL query on the database and return results with column names"""
        results = {"columns": [], "rows": [], "status": "", "execution_time": None}
        start_time = datetime.now()
        
        try:
            print(query)
            conn = self.create_connection(database_obj)
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                
                # Calculate execution time
                execution_time = (datetime.now() - start_time).total_seconds()
                results["execution_time"] = execution_time
                
                # Check if query returns data
                if cursor.description:
                    # Get column names
                    results["columns"] = [desc[0] for desc in cursor.description]
                    
                    # Get all rows
                    rows = cursor.fetchall()
                    # Convert any non-serializable types to strings
                    formatted_rows = []
                    for row in rows:
                        formatted_row = []
                        for value in row:
                            if isinstance(value, (datetime, pytz.datetime.datetime)):
                                formatted_row.append(value.strftime('%Y-%m-%d %H:%M:%S'))
                            else:
                                formatted_row.append(value)
                        formatted_rows.append(formatted_row)
                    
                    results["rows"] = formatted_rows
                    results["status"] = f"Query returned {len(formatted_rows)} rows"
                else:
                    # For non-SELECT queries
                    affected_rows = cursor.rowcount
                    conn.commit()
                    results["status"] = f"Query executed successfully. Affected rows: {affected_rows}"
            
            conn.close()
            database_obj.connection_status = 'disconnected'  # Set to disconnected after query
            database_obj.save(update_fields=['connection_status'])
            results["success"] = True
            return results
        except Exception as e:
            # Calculate execution time even for failed queries
            execution_time = (datetime.now() - start_time).total_seconds()
            results["execution_time"] = execution_time
            
            # Set default error information
            results["success"] = False
            results["status"] = f"Error: {str(e)}"
            results["error_type"] = "execution_error"  # Default error type
            
            # Try to classify the error more specifically
            error_message = str(e).lower()
            
            if "syntax error" in error_message:
                results["error_type"] = "syntax_error"
            elif "permission denied" in error_message or "access denied" in error_message:
                results["error_type"] = "permission_error"
            elif "does not exist" in error_message and "relation" in error_message:
                results["error_type"] = "undefined_table"
            elif "column" in error_message and "does not exist" in error_message:
                results["error_type"] = "undefined_column"
            elif "connection" in error_message:
                results["error_type"] = "connection_error"
            elif "timeout" in error_message:
                results["error_type"] = "timeout_error"
            elif "duplicate key" in error_message:
                results["error_type"] = "duplicate_key_error"
            elif "violates foreign key constraint" in error_message:
                results["error_type"] = "foreign_key_violation"
            elif "division by zero" in error_message:
                results["error_type"] = "division_by_zero"
            
            database_obj.connection_status = 'error'
            database_obj.save(update_fields=['connection_status'])
            return results
    
    def get_column_sample_values(self, database_obj, schema_name, table_name, column_name, limit=10):
        """Fetch sample distinct values from a column to provide AI context"""
        try:
            conn = self.create_connection(database_obj)
            results = []
            
            with conn.cursor() as cursor:
                # Use SQL DISTINCT to get unique values, limit to 10 for context
                query = f"""
                SELECT DISTINCT "{column_name}" 
                FROM "{schema_name}"."{table_name}"
                WHERE "{column_name}" IS NOT NULL
                LIMIT {limit}
                """
                
                try:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        # Handle different data types for serialization
                        value = row[0]
                        if isinstance(value, (datetime, pytz.datetime.datetime)):
                            value = value.strftime('%Y-%m-%d %H:%M:%S')
                        
                        results.append(value)
                except Exception as e:
                    # If query fails, just return empty list
                    print(f"Error getting sample values: {str(e)}")
            
            conn.close()
            return results
        except Exception as e:
            print(f"Connection error getting sample values: {str(e)}")
            return []

class MetadataExtractor:
    """Extracts schema metadata from connected databases"""
    
    def __init__(self):
        self.connector = DatabaseConnector()
        self.changes = {
            'tables': {'added': [], 'updated': [], 'removed': []},
            'columns': {'added': [], 'updated': [], 'removed': []},
            'relationships': {'added': [], 'updated': [], 'removed': []}
        }
    
    def extract_full_metadata(self, database_obj):
        """Extract all metadata (tables, columns, relationships) from a database"""
        try:
            # Reset changes tracking
            self.changes = {
                'tables': {'added': [], 'updated': [], 'removed': []},
                'columns': {'added': [], 'updated': [], 'removed': []},
                'relationships': {'added': [], 'updated': [], 'removed': []}
            }
            
            # Get all current tables in database to track removed tables
            existing_tables = set(TableMetadata.objects.filter(database=database_obj)
                                 .values_list('schema_name', 'table_name'))
            
            # Get tables first
            tables = self.extract_tables(database_obj)
            
            # Check for removed tables
            current_tables = set((table.schema_name, table.table_name) for table in tables)
            removed_tables = existing_tables - current_tables
            
            # Record removed tables
            for schema_name, table_name in removed_tables:
                try:
                    table = TableMetadata.objects.get(
                        database=database_obj,
                        schema_name=schema_name,
                        table_name=table_name
                    )
                    self.changes['tables']['removed'].append({
                        'schema': schema_name,
                        'name': table_name
                    })
                    table.delete()
                except TableMetadata.DoesNotExist:
                    continue  # Table was already deleted somehow
            
            # For each table, get its columns
            for table in tables:
                # Get current columns in table to track removed columns
                existing_columns = set(
                    ColumnMetadata.objects.filter(table=table)
                    .values_list('column_name', flat=True)
                )
                
                # Extract columns
                columns = self.extract_columns(database_obj, table.schema_name, table.table_name)
                
                # Check for removed columns
                current_columns = set(col.column_name for col in columns)
                removed_columns = existing_columns - current_columns
                
                # Record removed columns
                for column_name in removed_columns:
                    try:
                        column = ColumnMetadata.objects.get(
                            table=table,
                            column_name=column_name
                        )
                        self.changes['columns']['removed'].append({
                            'table': f"{table.schema_name}.{table.table_name}",
                            'name': column_name
                        })
                        column.delete()
                    except ColumnMetadata.DoesNotExist:
                        continue  # Column was already deleted
            
            # Extract relationships between tables
            self.extract_relationships(database_obj)
            
            # Update the timestamp for metadata update
            database_obj.last_metadata_update = datetime.now(pytz.UTC)
            database_obj.save(update_fields=['last_metadata_update'])
            
            return True, "Metadata extraction completed successfully", self.changes
        except Exception as e:
            return False, str(e), self.changes
    
    def extract_tables(self, database_obj, schema_pattern=None):
        """Extract tables and views from the database"""
        tables = []
        
        try:
            conn = self.connector.create_connection(database_obj)
            with conn.cursor() as cursor:
                query = """
                SELECT 
                    table_schema, 
                    table_name, 
                    table_type,
                    obj_description(
                        (quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass::oid, 
                        'pg_class'
                    ) as description
                FROM 
                    information_schema.tables 
                WHERE 
                    table_schema NOT IN ('pg_catalog', 'information_schema')
                """
                
                if schema_pattern:
                    query += " AND table_schema LIKE %s"
                    cursor.execute(query, (schema_pattern,))
                else:
                    cursor.execute(query)
                
                for row in cursor.fetchall():
                    schema_name, table_name, table_type, db_description = row
                    
                    # Convert PostgreSQL table_type to our format
                    if table_type == 'BASE TABLE':
                        table_type = 'table'
                    elif table_type == 'VIEW':
                        table_type = 'view'
                    elif table_type == 'MATERIALIZED VIEW':
                        table_type = 'materialized_view'
                    
                    # Try to find existing table metadata to preserve description
                    try:
                        existing_table = TableMetadata.objects.get(
                            database=database_obj,
                            schema_name=schema_name,
                            table_name=table_name
                        )
                        # Preserve existing description if it exists and not empty
                        description = existing_table.description if existing_table.description else db_description
                    except TableMetadata.DoesNotExist:
                        description = db_description if db_description else ""
                    
                    # Get or create table metadata record
                    table_meta, created = TableMetadata.objects.update_or_create(
                        database=database_obj,
                        schema_name=schema_name,
                        table_name=table_name,
                        defaults={
                            'table_type': table_type,
                            'description': description
                        }
                    )
                    
                    # Generate default description if none exists
                    if not table_meta.description:
                        table_meta.description = self.generate_table_description(table_meta)
                        table_meta.save(update_fields=['description'])
                    
                    # Track changes
                    if created:
                        self.changes['tables']['added'].append({
                            'schema': schema_name,
                            'name': table_name,
                            'type': table_type
                        })
                    elif table_meta.table_type != table_type:
                        # Only count as update if table type changed, not description
                        self.changes['tables']['updated'].append({
                            'schema': schema_name,
                            'name': table_name,
                            'type': table_type,
                            'changes': {
                                'type': table_type if table_meta.table_type != table_type else None,
                            }
                        })
                    
                    # Get row count for tables (not views)
                    if table_type == 'table':
                        try:
                            count_query = f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"'
                            cursor.execute(count_query)
                            row_count = cursor.fetchone()[0]
                            if table_meta.row_count != row_count:
                                table_meta.row_count = row_count
                                table_meta.save(update_fields=['row_count'])
                        except:
                            # Skip row count if it fails
                            pass
                    
                    tables.append(table_meta)
            
            conn.close()
            return tables
        
        except Exception as e:
            # Cleanup connection and re-raise
            if 'conn' in locals() and conn:
                conn.close()
            raise e
    
    def extract_columns(self, database_obj, schema_name, table_name):
        """Extract column metadata for a specific table"""
        columns = []
        
        try:
            conn = self.connector.create_connection(database_obj)
            table = TableMetadata.objects.get(
                database=database_obj, 
                schema_name=schema_name, 
                table_name=table_name
            )
            
            with conn.cursor() as cursor:
                # Get column information
                cursor.execute("""
                SELECT 
                    column_name, 
                    data_type,
                    is_nullable,
                    column_default,
                    col_description(
                        (quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass::oid,
                        ordinal_position
                    ) as description
                FROM 
                    information_schema.columns
                WHERE 
                    table_schema = %s AND table_name = %s
                ORDER BY 
                    ordinal_position
                """, (schema_name, table_name))
                
                for row in cursor.fetchall():
                    column_name, data_type, is_nullable, column_default, db_description = row
                    is_nullable = True if is_nullable == 'YES' else False
                    
                    # Check if column is primary key
                    cursor.execute("""
                    SELECT 
                        c.column_name
                    FROM 
                        information_schema.table_constraints tc
                    JOIN 
                        information_schema.constraint_column_usage AS ccu 
                        USING (constraint_schema, constraint_name)
                    JOIN 
                        information_schema.columns AS c 
                        ON c.table_schema = tc.constraint_schema
                        AND c.table_name = tc.table_name
                        AND c.column_name = ccu.column_name
                    WHERE 
                        tc.constraint_type = 'PRIMARY KEY'
                        AND tc.table_schema = %s
                        AND tc.table_name = %s
                        AND ccu.column_name = %s
                    """, (schema_name, table_name, column_name))
                    
                    is_primary_key = bool(cursor.fetchone())
                    
                    # Check if column is foreign key
                    cursor.execute("""
                    SELECT 
                        ccu.table_schema, 
                        ccu.table_name, 
                        ccu.column_name
                    FROM 
                        information_schema.table_constraints AS tc
                    JOIN 
                        information_schema.constraint_column_usage AS ccu
                        USING (constraint_schema, constraint_name)
                    JOIN 
                        information_schema.key_column_usage AS kcu
                        USING (constraint_schema, constraint_name)
                    WHERE 
                        tc.constraint_type = 'FOREIGN KEY'
                        AND kcu.table_schema = %s
                        AND kcu.table_name = %s
                        AND kcu.column_name = %s
                    """, (schema_name, table_name, column_name))
                    
                    is_foreign_key = bool(cursor.fetchone())
                    
                    # Try to find existing column to preserve its description
                    try:
                        existing_column = ColumnMetadata.objects.get(
                            table=table,
                            column_name=column_name
                        )
                        # Preserve existing description if it exists
                        description = existing_column.description if existing_column.description else db_description
                    except ColumnMetadata.DoesNotExist:
                        description = db_description if db_description else ""
                    
                    # Create or update column metadata
                    column_meta, created = ColumnMetadata.objects.update_or_create(
                        table=table,
                        column_name=column_name,
                        defaults={
                            'data_type': data_type,
                            'is_nullable': is_nullable,
                            'is_primary_key': is_primary_key,
                            'is_foreign_key': is_foreign_key,
                            'description': description
                        }
                    )
                    
                    # Generate default description if none exists
                    if not column_meta.description:
                        column_meta.description = self.generate_column_description(column_meta)
                        column_meta.save(update_fields=['description'])
                    
                    # Track changes
                    if created:
                        self.changes['columns']['added'].append({
                            'table': f"{schema_name}.{table_name}",
                            'name': column_name,
                            'type': data_type
                        })
                    else:
                        changes = {}
                        if column_meta.data_type != data_type:
                            changes['type'] = data_type
                        if column_meta.is_nullable != is_nullable:
                            changes['nullable'] = is_nullable
                        if column_meta.is_primary_key != is_primary_key:
                            changes['primary_key'] = is_primary_key
                        if column_meta.is_foreign_key != is_foreign_key:
                            changes['foreign_key'] = is_foreign_key
                        
                        # Don't include description in changes since we're preserving it
                            
                        if changes:
                            self.changes['columns']['updated'].append({
                                'table': f"{schema_name}.{table_name}",
                                'name': column_name,
                                'changes': changes
                            })
                    
                    columns.append(column_meta)
            
            conn.close()
            return columns
        
        except Exception as e:
            # Cleanup connection and re-raise
            if 'conn' in locals() and conn:
                conn.close()
            raise e
    
    def extract_relationships(self, database_obj):
        """Extract relationships between tables in the database"""
        try:
            conn = self.connector.create_connection(database_obj)
            with conn.cursor() as cursor:
                # Query to find foreign key relationships
                cursor.execute("""
                SELECT
                    kcu.table_schema as fk_schema,
                    kcu.table_name as fk_table,
                    kcu.column_name as fk_column,
                    ccu.table_schema as pk_schema,
                    ccu.table_name as pk_table,
                    ccu.column_name as pk_column,
                    tc.constraint_name
                FROM
                    information_schema.table_constraints tc
                JOIN
                    information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN
                    information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE
                    tc.constraint_type = 'FOREIGN KEY'
                    AND kcu.table_schema NOT IN ('pg_catalog', 'information_schema')
                """)
                
                for row in cursor.fetchall():
                    fk_schema, fk_table, fk_column, pk_schema, pk_table, pk_column, constraint_name = row
                    
                    try:
                        # Get the table metadata objects
                        fk_table_meta = TableMetadata.objects.get(
                            database=database_obj,
                            schema_name=fk_schema,
                            table_name=fk_table
                        )
                        
                        pk_table_meta = TableMetadata.objects.get(
                            database=database_obj,
                            schema_name=pk_schema,
                            table_name=pk_table
                        )
                        
                        # Get the column metadata objects
                        from_column = ColumnMetadata.objects.get(
                            table=fk_table_meta,
                            column_name=fk_column
                        )
                        
                        to_column = ColumnMetadata.objects.get(
                            table=pk_table_meta,
                            column_name=pk_column
                        )
                        
                        # Create or update relationship
                        relationship, created = RelationshipMetadata.objects.update_or_create(
                            from_column=from_column,
                            to_column=to_column,
                            defaults={
                                'relationship_type': 'many-to-one'  # Assuming foreign keys create many-to-one relationships
                            }
                        )
                    except (TableMetadata.DoesNotExist, ColumnMetadata.DoesNotExist):
                        # Skip if the tables or columns aren't in our metadata yet
                        continue
            
            conn.close()
            return True
        
        except Exception as e:
            # Cleanup connection and re-raise
            if 'conn' in locals() and conn:
                conn.close()
            raise e
    
    def generate_table_description(self, table_metadata):
        """Generate natural language description of table (placeholder)"""
        return f"Table {table_metadata.schema_name}.{table_metadata.table_name} containing data related to {table_metadata.table_name.lower().replace('_', ' ')}."
    
    def generate_column_description(self, column_metadata):
        """Generate natural language description of column (placeholder)"""
        column_type = f"of type {column_metadata.data_type}"
        nullability = "nullable" if column_metadata.is_nullable else "not nullable"
        key_info = ""
        
        if column_metadata.is_primary_key:
            key_info = " and serves as the primary key"
        elif column_metadata.is_foreign_key:
            key_info = " and references another table"
            
        # Get sample values for the column
        sample_values = []
        try:
            connector = DatabaseConnector()
            table = column_metadata.table
            database = table.database
            sample_values = connector.get_column_sample_values(
                database,
                table.schema_name,
                table.table_name,
                column_metadata.column_name,
                limit=10
            )
        except Exception as e:
            print(f"Error getting sample values for default description: {str(e)}")
        
        # Include sample values in description if available
        sample_text = ""
        if sample_values:
            formatted_samples = [f"'{str(value)}'" for value in sample_values]
            if len(formatted_samples) > 5:
                # For more than 5 samples, show first 5 and indicate more exist
                sample_text = f" Sample values include: {', '.join(formatted_samples[:5])}, etc."
            else:
                # For 5 or fewer, show all
                sample_text = f" Sample values include: {', '.join(formatted_samples)}."
            
        return f"Column {column_metadata.column_name} {column_type} ({nullability}){key_info}.{sample_text}"

class MetadataVectorizer:
    """Creates vector embeddings for metadata for RAG"""
    
    def __init__(self):
        self.extractor = MetadataExtractor()
        self.cache = {}  # Simple in-memory cache for embeddings
    
    def create_table_embedding(self, table_metadata):
        """Generate embedding vector for table (placeholder)"""
        # In a real implementation, this would use an embedding model
        # For now, just create a placeholder JSON structure
        
        # Check if we have a cached embedding
        cache_key = f"table_{table_metadata.id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Generate a description if none exists
        description = table_metadata.description
        if not description:
            description = self.extractor.generate_table_description(table_metadata)
            table_metadata.description = description
            table_metadata.save(update_fields=['description'])
        
        # Create a simple embedding structure
        # This would be replaced with actual vector embeddings in production
        embedding = {
            "type": "table",
            "name": table_metadata.table_name,
            "schema": table_metadata.schema_name,
            "description": description,
            "vector_placeholder": [0.1, 0.2, 0.3]  # Placeholder for actual embedding vector
        }
        
        # Save the embedding to the database
        table_metadata.embedding_vector = embedding
        table_metadata.save(update_fields=['embedding_vector'])
        
        # Cache the result
        self.cache[cache_key] = embedding
        
        return embedding
    
    def create_column_embedding(self, column_metadata):
        """Generate embedding vector for column (placeholder)"""
        # In a real implementation, this would use an embedding model
        
        # Check if we have a cached embedding
        cache_key = f"column_{column_metadata.id}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Generate a description if none exists
        description = column_metadata.description
        if not description:
            description = self.extractor.generate_column_description(column_metadata)
            column_metadata.description = description
            column_metadata.save(update_fields=['description'])
        
        # Include table information
        table = column_metadata.table
        
        # Create a simple embedding structure
        # This would be replaced with actual vector embeddings in production
        embedding = {
            "type": "column",
            "name": column_metadata.column_name,
            "table": table.table_name,
            "schema": table.schema_name,
            "data_type": column_metadata.data_type,
            "is_primary_key": column_metadata.is_primary_key,
            "is_foreign_key": column_metadata.is_foreign_key,
            "description": description,
            "vector_placeholder": [0.4, 0.5, 0.6]  # Placeholder for actual embedding vector
        }
        
        # Save the embedding to the database
        column_metadata.embedding_vector = embedding
        column_metadata.save(update_fields=['embedding_vector'])
        
        # Cache the result
        self.cache[cache_key] = embedding
        
        return embedding
    
    def update_all_embeddings(self, database_obj):
        """Update all embeddings for a database"""
        try:
            # Clear cache for this database
            self.clear_cache_for_database(database_obj)
            
            # Get all tables
            tables = TableMetadata.objects.filter(database=database_obj)
            for table in tables:
                # Create table embedding
                self.create_table_embedding(table)
                
                # Create column embeddings for all columns in this table
                columns = ColumnMetadata.objects.filter(table=table)
                for column in columns:
                    self.create_column_embedding(column)
            
            return True, "Embeddings updated successfully"
        except Exception as e:
            return False, str(e)
    
    def clear_cache_for_database(self, database_obj):
        """Clear the embedding cache for a specific database"""
        # Get all tables for this database
        table_ids = TableMetadata.objects.filter(database=database_obj).values_list('id', flat=True)
        
        # Get all columns for these tables
        column_ids = ColumnMetadata.objects.filter(table__in=table_ids).values_list('id', flat=True)
        
        # Clear cache entries
        keys_to_remove = []
        for key in self.cache.keys():
            if key.startswith('table_') and int(key[6:]) in table_ids:
                keys_to_remove.append(key)
            elif key.startswith('column_') and int(key[7:]) in column_ids:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.cache[key]
    
    def search_metadata(self, database_obj, query_text, limit=10):
        """Search metadata based on text similarity (placeholder)"""
        # In a real implementation, this would use vector similarity search
        # For this skeleton, we'll just do a simple text match
        
        results = []
        
        # Search in tables
        tables = TableMetadata.objects.filter(database=database_obj)
        for table in tables:
            score = 0
            if query_text.lower() in table.table_name.lower():
                score += 5
            if table.description and query_text.lower() in table.description.lower():
                score += 3
            
            if score > 0:
                results.append({
                    'type': 'table',
                    'id': table.id,
                    'name': table.table_name,
                    'schema': table.schema_name,
                    'description': table.description,
                    'score': score
                })
        
        # Search in columns
        columns = ColumnMetadata.objects.filter(table__database=database_obj)
        for column in columns:
            score = 0
            if query_text.lower() in column.column_name.lower():
                score += 4
            if column.description and query_text.lower() in column.description.lower():
                score += 2
            # Give some score to data type matches
            if query_text.lower() in column.data_type.lower():
                score += 1
            
            if score > 0:
                results.append({
                    'type': 'column',
                    'id': column.id,
                    'name': column.column_name,
                    'table_name': column.table.table_name,
                    'schema': column.table.schema_name,
                    'data_type': column.data_type,
                    'description': column.description,
                    'score': score
                })
        
        # Sort by score (descending) and limit results
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

def generate_er_diagram(database_id):
    """
    Generate an ER diagram representation for a database in JSON format
    
    Args:
        database_id (int): The database ID to generate diagram for
        
    Returns:
        dict: JSON representation of the database ER diagram
    """
    try:
        from .models import TableMetadata, ColumnMetadata, RelationshipMetadata, ClientDatabase, ERDiagram
        from datetime import datetime

        # Get database schema information
        tables = TableMetadata.objects.filter(database_id=database_id)
        
        if not tables:
            return {
                "success": False, 
                "error": "No schema information available for this database"
            }
        
        # Build nodes (tables)
        nodes = []
        node_positions = {}
        
        # Calculate initial positions for tables
        grid_size = int(len(tables) ** 0.5) + 1
        grid_spacing = 300
        
        for i, table in enumerate(tables):
            # Calculate grid position
            row = i // grid_size
            col = i % grid_size
            
            # Generate a unique ID for this table
            table_id = f"{table.schema_name}.{table.table_name}"
            
            # Create position
            position = {
                'x': col * grid_spacing, 
                'y': row * grid_spacing
            }
            
            # Store position
            node_positions[table_id] = position
            
            columns = ColumnMetadata.objects.filter(table=table)
            column_info = []
            
            for column in columns:
                column_info.append({
                    'name': column.column_name,
                    'type': column.data_type,
                    'is_nullable': column.is_nullable,
                    'is_primary_key': column.is_primary_key,
                    'is_foreign_key': column.is_foreign_key,
                    'description': column.description if column.description else ""
                })
            
            # Create node
            nodes.append({
                "id": table_id,
                "type": "tableNode",
                "position": position,
                "data": {
                    "label": table.table_name,
                    "schema": table.schema_name,
                    "description": table.description if table.description else "",
                    "columns": column_info
                },
                "width": 220,
                "height": 40 + len(column_info) * 24  # Dynamic height based on number of columns
            })
        
        # Build edges (relationships)
        edges = []
        
        # Get relationships
        relationships = RelationshipMetadata.objects.filter(
            from_column__table__database_id=database_id
        )
        
        for rel in relationships:
            from_table = rel.from_column.table
            to_table = rel.to_column.table
            
            source_id = f"{from_table.schema_name}.{from_table.table_name}"
            target_id = f"{to_table.schema_name}.{to_table.table_name}"
            
            edge_id = f"e-{rel.from_column.id}-{rel.to_column.id}"
            
            edges.append({
                "id": edge_id,
                "source": source_id,
                "target": target_id,
                "animated": True,
                "style": {
                    "stroke": "#7C4DFF",
                    "strokeWidth": 2
                },
                "markerEnd": {
                    "type": "arrowclosed",
                    "color": "#7C4DFF"
                },
                "data": {
                    "from_column": rel.from_column.column_name,
                    "to_column": rel.to_column.column_name,
                    "relationship_type": rel.relationship_type,
                    "label": f"{rel.from_column.column_name} → {rel.to_column.column_name}"
                },
                "label": f"{rel.from_column.column_name} → {rel.to_column.column_name}"
            })
        
        # Create complete diagram data
        diagram_data = {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "database_id": database_id,
                "generated_at": datetime.now().isoformat()
            }
        }
        
        # Store the diagram data in the database
        database = ClientDatabase.objects.get(id=database_id)
        
        # Update or create ER diagram
        diagram, created = ERDiagram.objects.update_or_create(
            database=database,
            defaults={"diagram_data": diagram_data}
        )
        
        return {
            "success": True,
            "diagram_data": diagram_data
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}