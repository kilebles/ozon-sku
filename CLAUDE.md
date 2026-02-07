# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ozon-call is a Python 3.12 web scraping/automation tool that uses nodriver to parse data and exports results to Google Sheets.

## Commands

```bash
# Install dependencies (uses uv package manager)
uv sync

# Run the application
uv run python -m src.main
```

## Architecture

- **src/core/settings.py** - Pydantic Settings configuration, loads from `.env` file
- **src/services/sheets.py** - Google Sheets integration using gspread with service account auth
- **src/parser/** - Browser automation/parsing logic

## Configuration

Required environment variables in `.env`:
- `START_URL` - Target URL to parse
- `GOOGLE_SPREADSHEET_ID` - Google Sheets document ID
- `GOOGLE_SHEET_NAME` - Worksheet name within the spreadsheet

Required file:
- `credentials.json` - Google service account credentials (root of project)
