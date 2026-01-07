# LLM Query System

A natural language to SQL query interface powered by large language models that helps users interact with PostgreSQL databases using plain English.

## Features

- **Natural Language to SQL**: Convert English questions into SQL queries
- **Multiple Database Support**: Connect and manage multiple PostgreSQL databases
- **Session Management**: Create and manage query sessions for different databases
- **Schema Introspection**: Automatically extract and visualize database schema
- **Relationship Visualization**: View and understand table relationships
- **Metadata Enhancement**: AI-powered descriptions for tables and columns
- **Query History**: Track and reuse previous queries
- **Dark Mode**: Built-in dark theme for comfortable use
- **Responsive Design**: Works seamlessly on desktop and mobile devices
- **Authentication**: Secure user authentication with Firebase

## Tech Stack

- **Frontend**: React + Vite
- **Backend**: Django + Django REST Framework
- **Database**: PostgreSQL
- **Authentication**: Firebase
- **UI Framework**: Material-UI
- **Styling**: Tailwind CSS

## Prerequisites

- Node.js >= 16
- Python >= 3.8
- PostgreSQL >= 12
- Firebase account

## Setup

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create `.env` file:
```bash
VITE_API_URL=http://localhost:8000
```

4. Start development server:
```bash
npm run dev
```

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file:
```bash
DEBUG=True
SECRET_KEY=your-secret-key
OPENAI_API_KEY=your-openai-api-key
```

5. Run migrations:
```bash
python manage.py migrate
```

6. Start development server:
```bash
python manage.py runserver
```

## Usage

1. Register/Login using email or Google account
2. Add a PostgreSQL database connection
3. Create a new query session
4. Start asking questions in natural language
5. View generated SQL and results
6. Manage sessions and database connections

## Project Structure

```
.
├── backend/
│   ├── databases/      # Database management app
│   ├── llm_agent/     # LLM integration app
│   └── user/          # User authentication app
└── frontend/
    ├── src/
    │   ├── components/
    │   ├── pages/
    │   ├── api/
    │   └── styles/
    └── public/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Material-UI for React components
- Firebase for authentication
- All other open-source contributors
