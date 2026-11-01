# Student Study Organiser

This is a beginner-friendly Django web app for tracking academic work and study progress.

## Current stage: student accounts, study planning, and assistant tools

Students can create an account, then store subjects, assignments, exams, projects, and study sessions in a local SQLite database. Each account only sees its own records. The dashboard calculates completion, overdue work, upcoming deadlines, and study time from saved records. It compares this week's logged minutes with last week's and offers explainable rule-based suggestions. The assistant can answer using the student's saved progress and prepare task changes for approval. The planner builds focus sessions from deadlines, priorities, and saved preferences.

### Run locally on Windows

Activate the project environment, apply database migrations, create an account in the browser, optionally add sample data to that account, and start Django's local server:

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py test
python manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/accounts/signup/` to create an account. The login page is at `/accounts/login/`. To add sample records to an existing account, use `python manage.py seed_demo_data --username YOUR_USERNAME`. The sample-data command is safe to repeat: it adds missing examples and does not overwrite or delete existing rows.

### Main pages

- `/` — completion, overdue and upcoming work, study-time comparisons, and explainable next-step suggestions.
- `/subjects/` — list subjects; use **Add subject** to create one.
- `/tasks/new/` — add an assignment, exam, or project.
- `/study-sessions/new/` — log time spent studying.
- `/assistant/` — chat about saved study progress and prepare task changes for approval.
- `/study-plan/` — generate an explainable, deadline-first suggestion within saved study availability.
- `/preferences/` — save the daily study time, focus-session length, and break defaults.
- The dashboard can ask your browser for permission to show a Windows desktop notification when a pending task is due today or tomorrow. The app must be open and visited for these local reminders to be checked.
- `/accounts/signup/` and `/accounts/login/` — create an account or sign in.

Task changes are validated by Django forms. Deletion first shows a confirmation page; the task is removed only after the confirmation form is submitted.

### Concepts introduced

- A Django **model** describes a record and its database fields.
- A **migration** is Django's versioned instruction for creating or changing tables.
- A **ModelForm** creates a form from a model and validates submitted values.
- A **view** loads records, calculates dashboard values, and chooses a template.
- A Django `TestCase` checks database behavior using a temporary test database.
- `academics/services/progress.py` keeps progress calculations separate from HTML rendering. Passing a date into the summary function makes week-boundary rules straightforward to test.
- Django's built-in authentication handles password hashing and login sessions. Every academic page requires sign-in, and queries/forms are scoped to the signed-in account.
- The study assistant uses OpenAI's Responses API with a small allowlist of function tools. Read tools are scoped to one account; task changes create a saved proposal and only apply after a signed-in student approves it.
- The planner is deterministic Python logic rather than an LLM guess: it sorts pending tasks by due date and priority, then divides estimated work into the student's preferred focus sessions. It only suggests sessions and does not update tasks or calendars.

### Enable the OpenAI assistant

The assistant needs the OpenAI SDK from `requirements.txt` and an API key in the process environment. In PowerShell, set the key without putting it in source code, then start the server in the same terminal:

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-6-astra"
python manage.py runserver 127.0.0.1:8000
```

The default model is configurable with `OPENAI_MODEL`. Do not commit a real key or put sensitive student information in messages. The app sends recent conversation messages and tool-requested account data to OpenAI to produce answers.

### Free cloud sync and deployment

For a learning prototype, the prepared deployment uses a Render Free web service for the Django app and a Supabase Free PostgreSQL database for shared data. The same online database lets one student account see its records from different devices. Local SQLite remains the default during development. The existing local demo data is not copied to the cloud; the deployed database starts empty.

This app is kept in the `student-study-organiser/` subfolder of the public `My_Projects` repository. Its source code and deployment configuration are therefore public. Never place student records, `.env` files, database URLs, or API keys in this repository. If the source code also needs to stay private, use a private repository instead.

Free services have limits. [Render's free web service](https://render.com/docs/free) sleeps after 15 minutes without a request, so the first visit after idle can take about a minute. [Supabase Free](https://supabase.com/pricing) currently includes a 500 MB database and can pause a project after a week of low activity. Free database projects do not include automatic backups, so keep a separate export of any data you care about. Treat this as a prototype and do not store sensitive or critical student records here.

#### Set up the services

1. Keep the app's files in its `student-study-organiser/` folder. Do not commit `.env`, database URLs, API keys, or student data.
2. Create a Supabase Free project. In the Supabase dashboard, open **Connect**, choose **Session pooler** (port `5432`), and copy its PostgreSQL connection URL. Supabase recommends this mode for persistent backends on IPv4-only networks. If your database password contains reserved URL characters, URL-encode them in the connection URL. Keep the URL private; it contains the database password. See [Supabase's connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres).
3. In Render, create a new Blueprint from the `My_Projects` repository and set Blueprint Path to `student-study-organiser/render.yaml`. The manifest's `rootDir` makes build and start commands run inside the app folder. When prompted for `DATABASE_URL`, paste the Supabase session-pooler URL into Render's private environment field. Do not add it to this README or commit it. The deployment uses TLS (`DATABASE_SSLMODE=require`).
4. Deploy the service. Render installs `requirements.txt`, collects static files, and runs Django migrations when the service starts. Check `/health/` for a small `{"status":"ok"}` response, then open the service URL and create a student account.
5. To use the AI assistant in the deployed app, add `OPENAI_API_KEY` as a private Render environment variable. `OPENAI_MODEL` is optional and defaults to the configured model name in `study_organiser/settings.py`. OpenAI API usage is billed separately from the free hosting, at the selected model's rates; review [current API pricing](https://openai.com/api/pricing/) before enabling it. Without the key, the rest of the organiser still works.

The manifest generates a production `DJANGO_SECRET_KEY` for the service. Render's public hostname is added to Django's allowed hosts and CSRF trusted origins at runtime. Keep the Supabase password and OpenAI key in provider environment settings only. If a credential is exposed, rotate it in the provider dashboard.

#### What deployment does not transfer or schedule

The first cloud database is empty, so create an account and re-enter any subjects or tasks you want online. Windows browser notifications are checked when the dashboard is open; the free web service does not send background Windows notifications while your computer or browser is closed. Deployment also does not create the Supabase project or Render service automatically: those accounts must be connected to the repository and database URL.

#### Local production-configuration check

The app has a `/health/` endpoint, WhiteNoise serves collected static files, and the Render startup command applies migrations before Gunicorn serves requests. For local development, continue using SQLite and the Windows commands above. Do not use Django's development server as a public production server.

