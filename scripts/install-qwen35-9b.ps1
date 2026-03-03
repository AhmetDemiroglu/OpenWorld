$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$modelsDir = Join-Path $root "models"
New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
$python = Join-Path $root "backend\\.venv\\Scripts\\python.exe"

$ggufName = "Qwen3.5-9B-Q4_K_M.gguf"
$ggufPath = Join-Path $modelsDir $ggufName
$url = "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/${ggufName}?download=true"
$env:OPENWORLD_GGUF_URL = $url
$env:OPENWORLD_GGUF_PATH = $ggufPath

if (-not (Test-Path $ggufPath)) {
  Write-Host "Downloading $ggufName ..."
  @"
import os
from pathlib import Path
import httpx

url = os.environ["OPENWORLD_GGUF_URL"]
out_path = Path(os.environ["OPENWORLD_GGUF_PATH"])
out_path.parent.mkdir(parents=True, exist_ok=True)

with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
    r.raise_for_status()
    with out_path.open("wb") as f:
        for chunk in r.iter_bytes():
            if chunk:
                f.write(chunk)
print("download_complete")
"@ | & $python -
  if ($LASTEXITCODE -ne 0) { throw "GGUF download failed." }
} else {
  Write-Host "GGUF already exists: $ggufPath"
}

Write-Host "GGUF ready for llama_cpp backend."

Write-Host "Removing default old model if present ..."
$exists = (ollama list | Select-String "qwen2.5:7b-instruct")
if ($exists) {
  ollama rm qwen2.5:7b-instruct | Out-Null
}

Write-Host "Done."
