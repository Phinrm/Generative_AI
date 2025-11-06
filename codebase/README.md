
# Codebase Genius - Documentation Assistant

A documentation generation and chat system powered by Google's Gemini AI that:
- Analyzes URLs and GitHub repositories
- Generates comprehensive Markdown documentation
- Provides an interactive chat interface to ask questions about the docs
- Supports downloading generated documentation

## Prerequisites
- Python 3.10+
- Git
- Google Cloud Project with Gemini API enabled

## Setup

1. Create and activate a Python virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2. Install backend dependencies:
```bash
cd BE
pip install -r requirements.txt
```

3. Install frontend dependencies:
```bash
cd ../FE
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.template .env
# Edit .env and add your GEMINI_API_KEY
```

## Running the Application

1. Start the backend server:
```bash
cd BE
jac serve main.jac
```
2. Start the backend server:
```bash
cd BE
uvicorn api_server:app --host 127.0.0.1 --port 8001 --reload
```

3. Start the Streamlit frontend (in a new terminal):
```bash
cd FE
streamlit run app.py
```

4. Open your browser to http://localhost:8501

## Features

### Documentation Generation
- Input any URL (GitHub repos, documentation pages, etc.)
- Automatic README detection for GitHub repositories
- Generated docs include:
  - Overview
  - Key features
  - Setup instructions
  - Usage examples
  - API documentation (when available)

### Interactive Chat
- Ask questions about the generated documentation
- Get clarification on specific points
- Explore implementation details
- Query for examples and use cases

### File Management
- All generated docs are saved to the `outputs/` directory
- Download documentation as Markdown files
- Load previously generated documentation

