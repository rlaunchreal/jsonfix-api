# JSON Repair & LLM Output Fixer API

JSONFix API is a deterministic FastAPI service that repairs broken JSON, JSON-like text, Markdown-wrapped JSON, and messy LLM output into clean, parseable JSON when possible.

It does **not** call OpenAI, Claude, Gemini, or any external AI model. Repairs are handled locally with normal JSON parsing, `json-repair`, and optional JSON Schema validation.

## RapidAPI Listing

**Suggested title:** JSON Repair & LLM Output Fixer API

**Suggested short description:** Fix broken JSON from ChatGPT, Claude, Gemini, scrapers, logs, and webhooks. Extract JSON from messy text, remove Markdown fences, repair trailing commas, quote keys, validate schemas, and return clean parseable JSON.

## Use Cases

- AI apps that need reliable JSON parsing from LLM responses
- Automation workflows that receive inconsistent payloads
- Webhooks with malformed or JSON-like bodies
- Scraper output cleanup
- Log and data cleaning pipelines
- Schema validation before storing or forwarding data

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Basic API info |
| `GET` | `/health` | Health check |
| `GET` | `/api-info` | API metadata for marketplaces |
| `POST` | `/repair` | Repair malformed JSON or Markdown-wrapped JSON |
| `POST` | `/extract` | Extract likely JSON from surrounding text |
| `POST` | `/validate` | Validate strict JSON without repair |
| `POST` | `/repair-with-schema` | Repair JSON and validate it against a JSON Schema |
| `POST` | `/batch-repair` | Repair up to 100 JSON strings in one request |

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Open the interactive docs at:

```text
http://127.0.0.1:8000/docs
```

## Request Examples

### Repair JSON

Request:

```json
{
  "text": "```json\n{name:'John', age:30,}\n```",
  "return_string": true
}
```

Response:

```json
{
  "success": true,
  "data": {
    "name": "John",
    "age": 30
  },
  "json_string": "{\"name\":\"John\",\"age\":30}",
  "fixes_applied": [
    "removed_markdown_fence",
    "repaired_json"
  ],
  "error": null
}
```

curl:

```bash
curl -X POST "http://127.0.0.1:8000/repair" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"```json\n{name:'John', age:30,}\n```\",\"return_string\":true}"
```

PowerShell:

```powershell
$body = @{
  text = "```json`n{name:'John', age:30,}`n```"
  return_string = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/repair" -Method Post -ContentType "application/json" -Body $body
```

### Extract JSON From Messy Text

Request:

```json
{
  "text": "Sure, here is your data: ```json\n{name:'Sarah', role:'Founder'}\n``` Thanks!"
}
```

Response:

```json
{
  "success": true,
  "json_found": true,
  "data": {
    "name": "Sarah",
    "role": "Founder"
  },
  "json_string": "{\"name\":\"Sarah\",\"role\":\"Founder\"}",
  "error": null
}
```

curl:

```bash
curl -X POST "http://127.0.0.1:8000/extract" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Sure, here is your data: ```json\n{name:'Sarah', role:'Founder'}\n``` Thanks!\"}"
```

PowerShell:

```powershell
$body = @{
  text = "Sure, here is your data: ```json`n{name:'Sarah', role:'Founder'}`n``` Thanks!"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/extract" -Method Post -ContentType "application/json" -Body $body
```

### Validate Strict JSON

Request:

```json
{
  "json_string": "{\"name\":\"John\",\"age\":30}"
}
```

Response:

```json
{
  "valid": true,
  "data": {
    "name": "John",
    "age": 30
  },
  "error": null
}
```

curl:

```bash
curl -X POST "http://127.0.0.1:8000/validate" \
  -H "Content-Type: application/json" \
  -d "{\"json_string\":\"{\\\"name\\\":\\\"John\\\",\\\"age\\\":30}\"}"
```

PowerShell:

```powershell
$body = @{
  json_string = '{"name":"John","age":30}'
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/validate" -Method Post -ContentType "application/json" -Body $body
```

### Repair With Schema

Request:

```json
{
  "text": "{name:'John', age:'30'}",
  "schema": {
    "type": "object",
    "required": ["name", "age"],
    "properties": {
      "name": {"type": "string"},
      "age": {"type": "number"}
    }
  }
}
```

Response:

```json
{
  "success": true,
  "data": {
    "name": "John",
    "age": 30
  },
  "schema_valid": true,
  "schema_errors": [],
  "json_string": "{\"name\":\"John\",\"age\":30}",
  "error": null
}
```

curl:

```bash
curl -X POST "http://127.0.0.1:8000/repair-with-schema" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"{name:'John', age:'30'}\",\"schema\":{\"type\":\"object\",\"required\":[\"name\",\"age\"],\"properties\":{\"name\":{\"type\":\"string\"},\"age\":{\"type\":\"number\"}}}}"
```

PowerShell:

```powershell
$body = @{
  text = "{name:'John', age:'30'}"
  schema = @{
    type = "object"
    required = @("name", "age")
    properties = @{
      name = @{ type = "string" }
      age = @{ type = "number" }
    }
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://127.0.0.1:8000/repair-with-schema" -Method Post -ContentType "application/json" -Body $body
```

### Batch Repair

Request:

```json
{
  "items": [
    "{name:'John'}",
    "{name:'Sarah', age:25,}"
  ]
}
```

Response:

```json
{
  "total": 2,
  "successful": 2,
  "failed": 0,
  "results": [
    {
      "index": 0,
      "success": true,
      "data": {"name": "John"},
      "json_string": "{\"name\":\"John\"}",
      "error": null
    },
    {
      "index": 1,
      "success": true,
      "data": {"name": "Sarah", "age": 25},
      "json_string": "{\"name\":\"Sarah\",\"age\":25}",
      "error": null
    }
  ]
}
```

curl:

```bash
curl -X POST "http://127.0.0.1:8000/batch-repair" \
  -H "Content-Type: application/json" \
  -d "{\"items\":[\"{name:'John'}\",\"{name:'Sarah', age:25,}\"]}"
```

PowerShell:

```powershell
$body = @{
  items = @(
    "{name:'John'}",
    "{name:'Sarah', age:25,}"
  )
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/batch-repair" -Method Post -ContentType "application/json" -Body $body
```

## Limits

- Maximum input text length: 200,000 characters
- Maximum batch size: 100 items
- `/validate` only accepts strict JSON and does not repair input
- JSONFix attempts to repair malformed JSON but cannot guarantee semantic correctness
- Schema validation depends on the schema provided by the caller

## Pricing Suggestion

For RapidAPI, a simple tiered model works well:

- **Free:** 100 requests/month for testing
- **Starter:** 10,000 requests/month
- **Pro:** 100,000 requests/month
- **Ultra:** Higher-volume plans with overage pricing

Because the API is deterministic and does not use external AI calls, pricing can be lower and more predictable than LLM-backed parsing tools.

## Render Deployment

This repository includes `render.yaml` for one-click Render deployment.

Render uses:

```text
Build command: pip install -r requirements.txt
Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

For RapidAPI proxy-only access, set this environment variable in Render:

```text
RAPIDAPI_PROXY_SECRET=your-rapidapi-proxy-secret
```

When this variable is set, paid endpoints require the `X-RapidAPI-Proxy-Secret` header. Public endpoints such as `/`, `/health`, `/api-info`, `/docs`, `/openapi.json`, and `/redoc` remain accessible.

After deployment, test:

```bash
curl "https://your-render-service.onrender.com/health"
```

## Notes for RapidAPI

RapidAPI handles authentication, rate limits, and subscriber access. This API intentionally does not include app-level authentication or database storage.
