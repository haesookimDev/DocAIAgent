# DocAIAgent Backend

AI-powered document and presentation generator backend using Python FastAPI.

## Features

- **Real-time slide generation**: LLM generates slides with SSE streaming
- **HTML preview**: See slides rendered as HTML in real-time
- **Export formats**: Download as PPTX, DOCX, or HTML
- **Multi-LLM support**: Works with Claude (Anthropic) and OpenAI GPT-4

## Quick Start

### 1. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and add your API keys:

```bash
cp .env.example .env
```

Edit `.env`:
```
ANTHROPIC_API_KEY=your-anthropic-api-key
OPENAI_API_KEY=your-openai-api-key
DEFAULT_LLM_PROVIDER=anthropic
```

### 3. Run the server

```bash
# From backend directory
python -m app.main

# Or with uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Access the application

- **Test UI**: http://localhost:8000/static/index.html
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## API Endpoints

### Runs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/runs` | Create a new generation run |
| GET | `/api/v1/runs/{run_id}` | Get run status |
| GET | `/api/v1/runs/{run_id}/stream` | SSE stream for real-time updates |
| POST | `/api/v1/runs/{run_id}/cancel` | Cancel a running generation |
| GET | `/api/v1/runs` | List all runs |

### Artifacts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/artifacts/{id}` | Get artifact metadata |
| GET | `/api/v1/artifacts/{id}/download?format=pptx` | Download as PPTX/DOCX/HTML |
| GET | `/api/v1/artifacts/{id}/preview` | HTML preview |
| GET | `/api/v1/artifacts/{id}/slidespec` | Raw SlideSpec JSON |

## Example Usage

### Create a presentation

```bash
curl -X POST http://localhost:8000/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "2024년 사업계획 발표자료를 만들어줘",
    "language": "ko",
    "slide_count": 10
  }'
```

### Stream generation events

```javascript
const eventSource = new EventSource('/api/v1/runs/{run_id}/stream');

eventSource.addEventListener('slide_chunk', (e) => {
  const data = JSON.parse(e.data);
  console.log('New slide HTML:', data.html);
});

eventSource.addEventListener('run_complete', (e) => {
  console.log('Generation complete!');
  eventSource.close();
});
```

### Download PPTX

```bash
curl -O "http://localhost:8000/api/v1/artifacts/{artifact_id}/download?format=pptx"
```

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── api/                 # API endpoints
│   │   ├── runs.py          # Run management & SSE streaming
│   │   └── artifacts.py     # Artifact download
│   ├── schemas/             # Pydantic models
│   │   ├── slidespec.py     # SlideSpec schema
│   │   └── run.py           # Run schemas
│   ├── services/            # Business logic
│   │   ├── llm_service.py   # LLM integration (Claude/OpenAI)
│   │   ├── agent_service.py # Slide generation agent
│   │   └── export_service.py # PPTX/DOCX export
│   ├── renderers/           # HTML rendering
│   │   └── html_slide_renderer.py
│   └── templates/           # Jinja2 templates
│       └── slides/          # 8 slide layouts
├── static/                  # Test UI
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── requirements.txt
└── .env.example
```

## Slide Layouts

The system supports 8 different slide layouts:

1. `title_center` - Title slides with centered text
2. `section_header` - Section divider slides
3. `one_column` - Single column content
4. `two_column` - Two column layout
5. `chart_focus` - Chart with key insights
6. `table_focus` - Table-focused layout
7. `quote_center` - Quote/highlight
8. `closing` - Thank you/closing slides

## SSE Event Types

| Event | Description |
|-------|-------------|
| `run_start` | Generation started |
| `run_progress` | Progress update with percentage |
| `slide_start` | Starting to generate a slide |
| `slide_chunk` | HTML content for a slide |
| `slide_complete` | Slide generation complete |
| `run_complete` | All slides generated |
| `run_error` | Error occurred |

## Development

### Run tests

```bash
pytest tests/
```

### Code structure

- **LLMService**: Unified interface for Claude/OpenAI
- **AgentService**: Orchestrates slide generation
- **HTMLSlideRenderer**: Converts SlideSpec to HTML
- **ExportService**: Converts to PPTX/DOCX

## License

MIT
