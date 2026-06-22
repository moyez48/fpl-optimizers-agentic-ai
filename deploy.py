"""
Upload the current repo tree to Hugging Face Spaces (surgical folder upload).

Requires: pip install huggingface_hub

Do not commit access tokens. Set HF_TOKEN before running:

  Windows (PowerShell):  $env:HF_TOKEN="hf_..."
  macOS/Linux:           export HF_TOKEN="hf_..."
"""

import os

from huggingface_hub import HfApi

HF_TOKEN_ENV = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")

repo_id = "moyez48/fpl-optimizer-api"


def _token():
    for name in HF_TOKEN_ENV:
        v = os.environ.get(name, "").strip()
        if v:
            return v
    raise SystemExit(
        "Missing HF token. Set environment variable HF_TOKEN (or HUGGING_FACE_HUB_TOKEN)."
    )


token = _token()

api = HfApi()

print("Starting upload to Hugging Face Space...")

api.upload_folder(
    folder_path=".",          # Upload current directory
    repo_id=repo_id,
    repo_type="space",
    token=token,
    # We ignore the frontend (app) and dev junk, but keep EVERYTHING else
    ignore_patterns=[
        ".git/*", 
        ".venv/*", 
        "__pycache__/*", 
        "app/*",        # Vercel handles the frontend
        "analysis/*",   # Notebooks/training scripts not needed on server
        "*.pyc"
    ]
)

print("✅ Success! Refresh your Hugging Face Space now.")