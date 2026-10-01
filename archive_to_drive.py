#!/usr/bin/env python3
"""
archive_to_drive.py — Archive the daily Stock-Team analyst reports to Google Drive,
organised into per-date folders, with byte-exact uploads (no truncation risk).

Folder layout created in Drive:
    My Drive/
      Stock Team Reports/
        2026-05-29/
          right_side_trading_2026-05-29.md
          short_term_report_2026-05-29.md
          long_term_strategy_2026-05-29.md
          elliott_wave_recommendations_2026-05-29.md
          chinese_principles_2026-05-29.md
          technical_macd_volume_2026-05-29.md
          whale_options_2026-05-29.md
          earnings_plays_2026-05-29.md
          Stock_Team_Summary_2026-05-29.md   (if present)

Why a script (and not the Drive MCP) for the raw reports:
  The Drive MCP requires file content to be passed *inline* as a tool argument,
  so a model has to re-emit every byte — slow, expensive, and risks silently
  truncating the 50-95 KB reports. This script streams the bytes straight from
  disk via the Drive REST API, so the upload is always exact.

------------------------------------------------------------------------------
ONE-TIME SETUP
------------------------------------------------------------------------------
1. Install deps:
       pip install google-api-python-client google-auth google-auth-oauthlib

2. Create an OAuth client (Desktop app) in Google Cloud Console for the Google
   account that owns the Drive you want to write to (e.g. markx5032@gmail.com):
       https://console.cloud.google.com/apis/credentials
   - Enable the "Google Drive API".
   - Create credentials -> OAuth client ID -> Application type: "Desktop app".
   - Download the JSON and save it next to this script as `client_secret.json`.

3. First run does a one-time browser consent and caches a refresh token to
   `token.json`. After that it runs head-less (the scheduled task can call it).

------------------------------------------------------------------------------
USAGE
------------------------------------------------------------------------------
    python archive_to_drive.py                  # archives today's reports
    python archive_to_drive.py --date 2026-05-29
    python archive_to_drive.py --date 2026-05-29 --overwrite
    python archive_to_drive.py --dir "C:/path/to/reports" --date 2026-05-29

Exit code 0 on success, non-zero on auth/upload failure (so the scheduled task
can fall back to the MCP summary-only path).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
ROOT_FOLDER_NAME = "Stock Team Reports"
FOLDER_MIME = "application/vnd.google-apps.folder"

# The 7 analyst reports + earnings bonus + the synthesized summary.
REPORT_PREFIXES = [
    "right_side_trading",
    "short_term_report",
    "long_term_strategy",
    "elliott_wave_recommendations",
    "chinese_principles",
    "technical_macd_volume",
    "whale_options",
    "earnings_plays",            # bonus
    "Stock_Team_Summary",        # synthesized digest, if written
]


def _here() -> Path:
    return Path(__file__).resolve().parent


def get_service():
    """Authenticate and return a Drive v3 service client."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:  # pragma: no cover
        sys.exit(
            "Missing dependency: %s\n"
            "Run: pip install google-api-python-client google-auth google-auth-oauthlib"
            % e
        )

    here = _here()
    token_path = here / "token.json"
    secret_path = here / "client_secret.json"
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secret_path.exists():
                sys.exit(
                    "No client_secret.json found at %s.\n"
                    "See the SETUP section at the top of this file." % secret_path
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_or_create_folder(service, name: str, parent_id: str | None = None) -> str:
    """Return the id of the folder `name` under `parent_id`, creating it if absent."""
    q = [f"name = '{name}'", f"mimeType = '{FOLDER_MIME}'", "trashed = false"]
    if parent_id:
        q.append(f"'{parent_id}' in parents")
    res = (
        service.files()
        .list(q=" and ".join(q), spaces="drive", fields="files(id, name)", pageSize=1)
        .execute()
    )
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    meta = {"name": name, "mimeType": FOLDER_MIME}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def _existing_file_id(service, name: str, parent_id: str) -> str | None:
    res = (
        service.files()
        .list(
            q=f"name = '{name}' and '{parent_id}' in parents and trashed = false",
            spaces="drive",
            fields="files(id, name)",
            pageSize=1,
        )
        .execute()
    )
    files = res.get("files", [])
    return files[0]["id"] if files else None


def upload_file(service, path: Path, parent_id: str, overwrite: bool) -> tuple[str, str]:
    """Upload `path` into `parent_id`. Returns (action, link)."""
    from googleapiclient.http import MediaFileUpload

    name = path.name
    mime = "text/markdown" if path.suffix.lower() == ".md" else "application/octet-stream"
    media = MediaFileUpload(str(path), mimetype=mime, resumable=True)

    existing = _existing_file_id(service, name, parent_id)
    if existing:
        if not overwrite:
            return ("skip (exists)", f"https://drive.google.com/file/d/{existing}/view")
        f = (
            service.files()
            .update(fileId=existing, media_body=media, fields="id, webViewLink")
            .execute()
        )
        return ("updated", f.get("webViewLink", ""))

    meta = {"name": name, "parents": [parent_id]}
    f = service.files().create(body=meta, media_body=media, fields="id, webViewLink").execute()
    return ("uploaded", f.get("webViewLink", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive daily stock reports to Google Drive.")
    ap.add_argument("--date", default=_dt.date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    ap.add_argument("--dir", default=str(_here()), help="Directory holding the report .md files")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite same-named files in Drive")
    args = ap.parse_args()

    report_dir = Path(args.dir)
    date = args.date

    paths = []
    for prefix in REPORT_PREFIXES:
        p = report_dir / f"{prefix}_{date}.md"
        if p.exists():
            paths.append(p)
    if not paths:
        print(f"[archive] No reports found for {date} in {report_dir}", file=sys.stderr)
        return 2

    service = get_service()
    root_id = find_or_create_folder(service, ROOT_FOLDER_NAME)
    date_id = find_or_create_folder(service, date, parent_id=root_id)
    folder_link = f"https://drive.google.com/drive/folders/{date_id}"

    print(f"[archive] Target folder: {ROOT_FOLDER_NAME}/{date}  ({folder_link})")
    for p in paths:
        action, link = upload_file(service, p, date_id, args.overwrite)
        print(f"  - {p.name:<42} {action:<16} {link}")

    print(f"[archive] Done. {len(paths)} file(s) processed -> {folder_link}")
    # Emit the folder link on the last line for easy capture by the caller.
    print(folder_link)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
