# Knowledge Vault

A lightweight searchable knowledge store for organising work notes, recurring solutions, and reference materials.

Knowledge entries can be grouped by category, tagged, searched, and linked to file attachments. The project includes a browser interface and a command-line client.

## Features

- Create, edit, and search knowledge entries
- Organise entries with categories and tags
- Full-text search across titles, content, and tags using SQLite FTS5
- Attach files to individual knowledge entries
- Browse categories and search results in the web interface
- Search and inspect entries through the CLI
- Back up the SQLite database and attachment files

## Technology

| Area | Stack |
| --- | --- |
| Backend | Python, FastAPI |
| Database and search | SQLite, FTS5 |
| Templates | Jinja2 |
| Runtime | uv, Uvicorn |

## Requirements

- Python 3.11 or later
- uv

## Install and run

    git clone https://github.com/BaeDoge/python-knowledge-store.git
    cd python-knowledge-store
    uv sync
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

Open http://127.0.0.1:8000.

On Windows, run.bat is also provided as a convenience launcher.

## CLI

The CLI communicates with a running Knowledge Vault server. Start the web application first, then inspect available commands:

    uv run python cli.py --help

The server address can be supplied through the CLI options.

## Data and backups

The application creates its runtime data directory automatically. It stores the SQLite database, uploaded attachments, and backup archives under data/. Back up the database and attachments together so that records and their files remain consistent.

The backup script is:

    backup.bat

## Security and intended use

The current project is a lightweight self-hosted tool and does not provide a full multi-user authentication or organisation-wide authorisation system. Run it on localhost or within a trusted network, and protect the host and data directory. Add authentication and access controls before exposing work materials to a public network.
