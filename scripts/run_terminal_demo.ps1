param(
    [string]$BackendUrl = 'http://localhost:8000',
    [string]$City = 'Irvine',
    [string]$State = 'California',
    [string]$Industry = 'Restaurants',
    [ValidateRange(1, 10)][int]$Count = 2
)

$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
$demoOutput = Join-Path $demoRoot 'output'
New-Item -ItemType Directory -Force $demoOutput | Out-Null
$demoBody = @{
    campaign = @{
        campaign_name = 'Terminal scraping demo'
        industries = @($Industry)
        cities_or_areas = @($City)
        state = $State
    }
    source_count = $Count
    lead_count = $Count
    persist_to_database = $false
} | ConvertTo-Json -Depth 5

Write-Host "Scraping $Industry in $City, $State. Database saving is disabled."
$demoResponse = Invoke-RestMethod -Method Post -Uri "$($BackendUrl.TrimEnd('/'))/run-sourcing-campaign" -ContentType 'application/json' -Body $demoBody -TimeoutSec 600
$demoFile = Join-Path $demoOutput 'actual-campaign-response.json'
$demoResponse | ConvertTo-Json -Depth 40 | Set-Content -Encoding utf8 $demoFile
$demoResponse.run_summary | Format-List
$demoPython = Join-Path $demoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) { $demoPython = 'python' }
& $demoPython (Join-Path $PSScriptRoot 'preview_sql_output.py') --input $demoFile
if ($LASTEXITCODE -ne 0) { throw 'Destination preview failed.' }
