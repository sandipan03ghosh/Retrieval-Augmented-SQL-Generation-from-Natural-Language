from openai import OpenAI
import os
import json
import logging
import requests
from django.conf import settings
from databases.models import TableMetadata, ColumnMetadata
from dotenv import load_dotenv
from django.contrib.auth.models import User
from user.models import UserTokenUsage

# load environment variables from .env file
load_dotenv()

def llm_api(prompt, model="gpt-4o-mini", temperature=0.7, max_tokens=1000, user=None):
    """
    A unified function to interact with either OpenAI or Groq API based on the model name.
    
    Args:
        prompt (str): The prompt to send to the API
        model (str): The model to use, default is gpt-4o-mini
        temperature (float): Controls randomness (0-1), default is 0.7
        max_tokens (int): Maximum number of tokens to generate, default is 1000
        user (User, optional): Django user to track token usage, default is None
        
    Returns:
        dict: The response with success status and content/error
    """
    logging.info(f"LLM API request with model: {model}")
    input_factor = 10

    try:
        # Check for OpenAI API key
        openai_api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
        groq_api_key = os.getenv("GROQ_API_KEY")
        
        # Determine which API to use based on available keys and model
        use_openai = model.startswith(("gpt", "o1", "o3")) and openai_api_key
        
        # If OpenAI model requested but no key, switch to Groq
        if model.startswith(("gpt", "o1", "o3")) and not openai_api_key:
            logging.warning("OpenAI model requested but no API key found. Switching to Groq with llama-3.1-8b-instant.")
            model = "llama-3.1-8b-instant"
            use_openai = False
        
        logging.info(f"Using {'OpenAI' if use_openai else 'Groq'} API with model {model}")
        
        if use_openai:
            # Initialize the OpenAI client
            client = OpenAI(api_key=openai_api_key)
            
            # Call the OpenAI API
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Extract the content from the response
            content = response.choices[0].message.content

            print(f"OpenAI usage data: {response.usage}")
            
            # Record token usage if user is provided
            if user and response.usage:
                UserTokenUsage.record_token_usage(
                    user=user,
                    prompt_tokens=response.usage.prompt_tokens/input_factor,
                    completion_tokens=response.usage.completion_tokens,
                    model=model,
                    query_text=prompt[:500]  # Store first 500 chars of the prompt
                )
                logging.info(f"Recorded token usage for {user.username}: {response.usage.prompt_tokens} prompt, {response.usage.completion_tokens} completion")
            
            return {
                "success": True,
                "content": content,
                "token_usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                    "model": model
                }
            }
        else:
            # Use Groq API
            if not groq_api_key:
                logging.error("Groq API key not found")
                return {
                    "success": False, 
                    "error": "Groq API key not found. Please set GROQ_API_KEY in your .env file.",
                    "error_type": "api_key_error"
                }
            
            # Set up the Groq request
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            
            # Ensure we're using a model that Groq supports
            groq_models = ["llama-3.1-8b-instant", "llama-3.1-70b-instant", "mixtral-8x7b-32768", "gemma-7b-it"]
            if model not in groq_models:
                logging.warning(f"Model {model} may not be supported by Groq. Using llama-3.1-8b-instant instead.")
                model = "llama-3.1-8b-instant"
            
            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            # Call the Groq API
            logging.info(f"Sending request to Groq API with model {model}")
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions", 
                    headers=headers, 
                    json=data,
                    timeout=30  # Add timeout to prevent hanging requests
                )
                response.raise_for_status()
                result = response.json()
                
                # Extract the content from the response
                content = result["choices"][0]["message"]["content"]

                # split by </think>
                content = content.split("</think>")[-1].strip()
                
                # Record token usage if user is provided and usage info is available
                if user and "usage" in result:
                    usage = result["usage"]
                    UserTokenUsage.record_token_usage(
                        user=user,
                        prompt_tokens=usage.get("prompt_tokens", 0)/input_factor,
                        completion_tokens=usage.get("completion_tokens", 0),
                        model=model,
                        query_text=prompt[:500]  # Store first 500 chars of the prompt
                    )
                    logging.info(f"Recorded token usage for {user.username}: {usage.get("prompt_tokens", 0)} prompt, {usage.get("completion_tokens", 0)} completion")
                
                # Extract token usage for return value
                token_usage = {
                    "prompt_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                    "completion_tokens": result.get("usage", {}).get("completion_tokens", 0),
                    "total_tokens": result.get("usage", {}).get("total_tokens", 0),
                    "model": model
                }
                
                return {
                    "success": True,
                    "content": content,
                    "token_usage": token_usage
                }
            except requests.exceptions.RequestException as e:
                logging.error(f"Error calling Groq API: {str(e)}")
                return {
                    "success": False, 
                    "error": f"Error calling Groq API: {str(e)}",
                    "error_type": "api_connection_error"
                }
            
    except Exception as e:
        logging.exception(f"Unexpected error in llm_api: {str(e)}")
        return {
            "success": False, 
            "error": f"Unexpected error: {str(e)}",
            "error_type": "general_llm_error"
        }

def get_metadata_description(metadata_type, name, sample_data=None, user=None):
    """
    Generate natural language descriptions for database metadata.
    
    Args:
        metadata_type (str): Type of metadata ('table', 'column', 'relationship')
        name (str): Name of the database object
        sample_data (dict, optional): Sample data or additional context
        user (User, optional): Django user to track token usage, default is None
        
    Returns:
        str: Generated description
    """
    # Base prompts without additional context
    base_prompts = {
        "table": f"Generate a brief, professional description for a database table named '{name}'.",
        "column": f"Generate a brief, professional description for a database column named '{name}'.",
        "relationship": f"Generate a brief, professional description for a database relationship."
    }
    
    if metadata_type not in base_prompts:
        return "Invalid metadata type specified."
    
    # Start with the base prompt
    prompt = base_prompts[metadata_type]
    
    # Add context details based on metadata type
    if sample_data:
        if metadata_type == 'table':
            schema = sample_data.get('schema', 'unknown')
            table_type = sample_data.get('table_type', 'table')
            row_count = sample_data.get('row_count', 'unknown')
            
            prompt += f"\n\nContext information:"
            prompt += f"\n- Schema: {schema}"
            prompt += f"\n- Table type: {table_type}"
            if row_count != 'unknown':
                prompt += f"\n- Approximate row count: {row_count}"
            
            # Add column information if available
            if 'columns' in sample_data:
                prompt += "\n- Columns:"
                for column in sample_data['columns'][:10]:  # Limit to 10 columns
                    col_name = column.get('name', '')
                    col_type = column.get('type', '')
                    is_pk = "primary key" if column.get('primary_key', False) else ""
                    is_fk = "foreign key" if column.get('foreign_key', False) else ""
                    
                    keys = ""
                    if is_pk and is_fk:
                        keys = " (primary and foreign key)"
                    elif is_pk:
                        keys = " (primary key)"
                    elif is_fk:
                        keys = " (foreign key)"
                        
                    prompt += f"\n  - {col_name}: {col_type}{keys}"
                    
        elif metadata_type == 'column':
            schema = sample_data.get('schema', 'unknown')
            table = sample_data.get('table', 'unknown')
            data_type = sample_data.get('data_type', 'unknown')
            nullable = "nullable" if sample_data.get('nullable', True) else "not nullable"
            
            prompt += f"\n\nContext information:"
            prompt += f"\n- Schema: {schema}"
            prompt += f"\n- Table: {table}"
            prompt += f"\n- Data type: {data_type}"
            prompt += f"\n- {nullable}"
            
            if sample_data.get('primary_key', False):
                prompt += "\n- This is a primary key column"
            
            if sample_data.get('foreign_key', False):
                prompt += "\n- This is a foreign key column"
            
            # Add sample values if available
            if 'sample_values' in sample_data and sample_data['sample_values']:
                sample_values = sample_data['sample_values']
                formatted_samples = [f"'{str(value)}'" for value in sample_values]
                prompt += f"\n\nSample distinct values from this column (up to 10): {', '.join(formatted_samples)}"
                prompt += "\n\nBased on the column name, data type, constraints, and especially these sample values, generate an accurate and specific description of what this column represents in the database."
                prompt += "\n\nYOUR DESCRIPTION MUST INCLUDE a brief mention of the possible values this column can contain, based on the provided sample values."
        
        elif metadata_type == 'relationship':
            prompt += f"\n\nContext information: {sample_data}"
    
    # Request a concise professional description
    prompt += "\n\nGenerate a single paragraph, professional description that would be helpful for a database user to understand this item's purpose and content."
    
    # Pass the user parameter to track token usage
    result = llm_api(prompt=prompt, user=user, model="llama-3.1-70b-instant")
    if result.get("success"):
        return result.get("content", "")
    return "Failed to generate description due to API error."

def nl_to_sql(natural_language_query, database_id, user=None):
    """
    Convert natural language query to SQL based on the provided database ID.
    Uses RAG (Retrieval-Augmented Generation) to enhance SQL generation with in-context learning.
    
    Args:
        natural_language_query (str): The natural language question
        database_id (int): Database ID to get schema information
        user (User, optional): Django user to track token usage, default is None
        
    Returns:
        dict: Generated SQL query and explanation
    """
    try:
        # Get the database to ensure it exists
        from databases.models import ClientDatabase
        try:
            database = ClientDatabase.objects.get(id=database_id)
        except ClientDatabase.DoesNotExist:
            return {
                "success": False,
                "error": f"Database with ID {database_id} does not exist.",
                "error_type": "database_not_found"
            }
            
        # Build schema representation from database
        schema = build_schema_representation(database_id)
        
        if not schema:
            # If metadata hasn't been extracted, inform the user
            return {
                "success": False,
                "error": "No schema information available for this database. Please extract metadata first by clicking 'Extract Schema' on the database details page.",
                "error_type": "metadata_not_extracted"
            }
        
        # Fetch similar examples using RAG to enhance in-context learning
        rag_examples = "" #get_rag_examples(natural_language_query)

        print(f"RAG examples: {rag_examples}")
        
        # Create a schema summary for the prompt
        schema_summary = json.dumps(schema, indent=2)
        
        # Build the prompt with in-context learning examples
        prompt = f"""
Given the following database schema:
```
{schema_summary}
```

"""
        prompt = prompt[:10000]  # Limit to 10000 characters for the prompt
        
        # Only include the RAG examples section if there are actually examples
        if rag_examples:
            prompt += f"""Here are some examples of natural language questions converted to SQL queries:
{rag_examples}

"""

        prompt += f"""Convert this natural language question to a valid SQL query:
"{natural_language_query}"

Return your answer as a JSON object with the following format:
{{
    "sql_query": "The SQL query",
    "explanation": "Brief explanation of what the query does"
}}
You must return only the json and nothing else.
"""
        # Pass the user to the LLM API call for token tracking
        result = llm_api(prompt, user=user, model="DeepSeek-R1-Distill-Llama-70B")
        
        if not result.get("success"):
            return {
                "success": False, 
                "error": result.get("error"), 
                "error_type": result.get("error_type", "llm_api_error")
            }
        
        content = result.get("content", "")
        try:
            if "```json" in content:
                json_content = content.split("```json")[1].split("```")[0].strip()
            elif "{" in content and "}" in content:
                json_content = "{" + content.split("{", 1)[1].split("}", 1)[0] + "}"
            else:
                json_content = content.strip()
                json_content = json_content.split("SELECT")[-1].strip()
                json_content = "SELECT " + json_content if json_content else ""
                json_content = json_content.split("\n\n")[0].strip().split("```")[0].strip()
                explanation = content.split("explanation:")[-1].strip().split("Explanation:")[-1].strip()
                json_content = f"""{{"sql_query": "{json_content}", "explanation": "{explanation if explanation else "No explanation available"}"}}"""
                
            response_data = json.loads(json_content)
            return {
                "success": True, 
                "sql_query": response_data.get("sql_query"), 
                "explanation": response_data.get("explanation")
            }
        except json.JSONDecodeError:
            # If we couldn't parse the output as JSON, return a generation error
            return {
                "success": False, 
                "error": "Failed to parse the generated SQL. The LLM output was in an unexpected format.",
                "error_type": "generation_error"
            }
    
    except Exception as e:
        logging.exception(f"Error in nl_to_sql: {str(e)}")
        error_message = str(e)
        error_type = "general_error"
        
        # Try to classify the error
        if "connection" in error_message.lower():
            error_type = "connection_error"
        elif "timeout" in error_message.lower():
            error_type = "timeout_error"
        elif "memory" in error_message.lower():
            error_type = "memory_error"
        
        return {
            "success": False, 
            "error": error_message,
            "error_type": error_type
        }

def build_schema_representation(database_id):
    """
    Build a representation of the database schema for the LLM based on extracted metadata.
    
    Args:
        database_id (int): The database ID
        
    Returns:
        list: Schema representation for the LLM
    """
    try:
        tables = TableMetadata.objects.filter(database_id=database_id)
        schema = []
        
        for table in tables:
            try:
                columns = ColumnMetadata.objects.filter(table=table)
                column_info = []
                
                for column in columns:
                    column_info.append({
                        'name': column.column_name,
                        'type': column.data_type,
                        'nullable': column.is_nullable,
                        'is_primary_key': column.is_primary_key,
                        'is_foreign_key': column.is_foreign_key,
                        'description': column.description if column.description else ""
                    })
                    
                schema.append({
                    'table_name': table.table_name,
                    'schema_name': table.schema_name,
                    'description': table.description if table.description else "",
                    'columns': column_info
                })
            except Exception as e:
                logging.error(f"Error processing table {table.table_name}: {str(e)}")
                continue
                
        if not schema:
            logging.warning(f"No schema information found for database ID {database_id}")
        
        return schema
        
    except Exception as e:
        logging.error(f"Error building schema representation: {str(e)}")
        return []

def get_rag_examples(query, top_k=5):
    """
    Fetch relevant question-answer pairs from the RAG server to use as examples
    for in-context learning.
    
    Args:
        query (str): The natural language query to find similar examples for
        top_k (int): Number of examples to retrieve
        
    Returns:
        str: Formatted string of example question-answer pairs
    """
    try:
        logging.info(f"Fetching RAG examples for query: {query}")
        
        # Make a request to the local RAG server
        rag_url = "http://localhost:8080/query"
        payload = {
            "text": query,
            "top_k": top_k
        }
        
        response = requests.post(rag_url, json=payload, timeout=10)
        
        if response.status_code != 200:
            logging.error(f"RAG server returned status code {response.status_code}")
            return ""
            
        result = response.json()
        documents = result.get("documents", [])
        
        if not documents:
            logging.warning("No examples found in RAG response")
            return ""
            
        # Format the examples for in-context learning
        examples_text = ""
        for i, doc in enumerate(documents):
            try:
                content = doc.get("content", {})
                question = content.get("question", "")
                answer = content.get("answer", "")
                
                if question and answer:
                    examples_text += f"Example {i+1}:\n"
                    examples_text += f"Question: \"{question}\"\n"
                    examples_text += f"SQL: {answer}\n\n"
            except Exception as e:
                logging.error(f"Error processing RAG document: {str(e)}")
                continue
        
        return examples_text
    
    except Exception as e:
        logging.exception(f"Error in get_rag_examples: {str(e)}")
        return ""
