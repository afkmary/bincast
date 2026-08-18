# BinCast Backend (Azure Function)

Receives sensor readings from the device, validates them against the team's
Data Contract, and stores them in Azure Table Storage.

## What's in this folder

- `function_app.py` — the HTTP endpoints (`/api/readings`, `/api/bins/{bin_id}/readings`, `/api/health`)
- `shared/validation.py` — checks every reading matches the Data Contract before it's stored
- `shared/table_storage.py` — talks to Azure Table Storage
- `requirements.txt` — Python packages needed
- `host.json` — Azure Functions config
- `local.settings.json.example` — copy this to `local.settings.json` and fill in real values (never commit the real file)
- `.github/workflows/deploy.yml` — auto-deploys to Azure every time you push to `main`

## Local setup (first time)

1. Install the Azure Functions Core Tools and Python 3.11 if you don't have them.
2. In this folder, create a virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate        (Windows)
   source .venv/bin/activate     (Mac/Linux)
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Copy the settings template and fill in your real connection strings:
   ```
   cp local.settings.json.example local.settings.json
   ```
   Get the storage connection string from the Azure Portal → your Storage Account → Access keys.
5. Run it locally:
   ```
   func start
   ```
6. Test it:
   ```
   curl -X POST http://localhost:7071/api/readings ^
     -H "Content-Type: application/json" ^
     -d "{\"bin_id\":\"bin-001\",\"timestamp\":\"2026-08-04T14:32:00Z\",\"raw_distance_cm\":42.7,\"fill_percentage\":63.5,\"bin_height_cm\":90.0,\"sensor_confidence\":0.92,\"connectivity_status\":\"Online\",\"buffered\":false,\"fill_rate_cm_per_hr\":1.8}"
   ```
   You should get back `{"status": "accepted", "bin_id": "bin-001"}`.

## Deploying to Azure (first time)

1. Create a Function App in the Azure Portal (Python 3.11, Consumption plan).
2. In the Function App → Configuration → Application settings, add:
   - `BINCAST_STORAGE_CONNECTION_STRING`
   - `APPLICATIONINSIGHTS_CONNECTION_STRING` (from the Application Insights resource)
3. Download the app's publish profile (Function App → Overview → "Get publish profile").
4. In the GitHub repo → Settings → Secrets → Actions, add a new secret:
   - Name: `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`
   - Value: paste the whole publish profile file
5. Edit `.github/workflows/deploy.yml` and replace `<your-function-app-name>` with your actual Function App name.
6. Push to `main` — GitHub Actions will deploy automatically. Check the "Actions" tab to watch it run.
7. Confirm it's live: `https://<your-function-app-name>.azurewebsites.net/api/health`

## Notes for the AI/ML side of the capstone vs. this project

This is the **BinCast** backend. Same pattern (Azure Function + validation + storage),
different schema and different repo — don't mix the two up when copying code.
