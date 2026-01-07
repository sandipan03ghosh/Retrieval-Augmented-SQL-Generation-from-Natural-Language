import axios from "axios";
import { ACCESS_TOKEN } from "./constants";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(ACCESS_TOKEN);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Session management functions - all endpoints are now under /api/ prefix
api.getSessions = () => api.get("/api/sessions/");
api.createSession = (title, database) =>
  api.post("/api/sessions/", { title, database });
api.getSession = (sessionId) => api.get(`/api/sessions/${sessionId}/`);
api.updateSessionTitle = (sessionId, title) =>
  api.patch(`/api/sessions/${sessionId}/`, { title });
api.deleteSession = (sessionId) => api.delete(`/api/sessions/${sessionId}/`);
api.addQueryToSession = (
  sessionId,
  prompt,
  response,
  success = true,
  errorType = null,
  error = null,
  generatedSql = null,
  explanation = null
) =>
  api.post(`/api/sessions/${sessionId}/queries/`, {
    prompt,
    response,
    success,
    error_type: errorType,
    error,
    generated_sql: generatedSql,
    explanation,
  });
api.updateQuery = (sessionId, queryId, updateData) =>
  api.patch(`/api/sessions/${sessionId}/queries/${queryId}/`, updateData);
api.deleteQueryFromSession = (sessionId, queryId) =>
  api.delete(`/api/sessions/${sessionId}/queries/${queryId}/`);

// Database management functions
api.getDatabases = () => api.get("/api/databases/databases/");
api.getDatabase = (databaseId) =>
  api.get(`/api/databases/databases/${databaseId}/`);
api.createDatabase = (databaseData) =>
  api.post("/api/databases/databases/", databaseData);
api.updateDatabase = (databaseId, databaseData) =>
  api.patch(`/api/databases/databases/${databaseId}/`, databaseData);
api.deleteDatabase = (databaseId) =>
  api.delete(`/api/databases/databases/${databaseId}/`);
api.testConnection = (databaseId) =>
  api.post(`/api/databases/databases/${databaseId}/test_connection/`);
api.refreshMetadata = (databaseId) =>
  api.post(`/api/databases/databases/${databaseId}/refresh_metadata/`);

// Metadata management functions
api.getTableMetadata = (databaseId) =>
  api.get(`/api/databases/databases/${databaseId}/tables/`);
api.updateTableMetadata = (tableId, metadata) =>
  api.patch(`/api/databases/tables/${tableId}/`, metadata);
api.getColumnMetadata = (tableId) =>
  api.get(`/api/databases/tables/${tableId}/columns/`);
api.updateColumnMetadata = (columnId, metadata) =>
  api.patch(`/api/databases/columns/${columnId}/`, metadata);

// Database metadata functions
api.getSessionsByDatabase = (databaseId) =>
  api.get(`/api/sessions/?database_id=${databaseId}`);
api.generateMetadataDescription = (databaseId, type, id) =>
  api.post(`/api/databases/databases/${databaseId}/generate_description/`, {
    type,
    id,
  });

// NL to SQL conversion
api.generateSqlFromNL = (query, databaseId) =>
  api.post("/api/llm/generate-sql/", {
    query,
    database_id: databaseId,
  });

// Execute SQL query
api.executeSqlQuery = (databaseId, sqlQuery) =>
  api.post(`/api/databases/databases/${databaseId}/execute_query/`, {
    query: sqlQuery,
  });

// ER Diagram
api.getERDiagram = (databaseId) =>
  api.get(`/api/databases/databases/${databaseId}/er_diagram/`);

// Token Usage
api.getTokenUsage = (days, limit) => {
  let url = "/api/user/token-usage/";
  const params = {};
  if (days) params.days = days;
  if (limit) params.limit = limit;
  return api.get(url, { params });
};

export default api;
