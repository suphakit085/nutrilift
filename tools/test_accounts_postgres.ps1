param(
    [string]$Python = ""
)

# Disposable local PostgreSQL only. This script does not use backend/.env's DB.
$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $workspace "backend"
if (-not $Python) { $Python = Join-Path $backend ".venv/Scripts/python.exe" }
if (-not (Test-Path -LiteralPath $Python)) { throw "Project Python not found: $Python" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is required" }
& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Start Docker Desktop and run this script again" }

$runId = [guid]::NewGuid().ToString("N")
$containerName = "nutrilift-auth-uat-$runId"
$labelKey = "nutrilift.auth-test-run"
$image = "pgvector/pgvector:pg16"
$artifactPath = Join-Path $workspace "output/postgres-auth/$runId"
$junitPath = Join-Path $artifactPath "pytest.xml"
New-Item -ItemType Directory -Path $artifactPath -Force | Out-Null
$previousEnvironment = @{}
$overrides = @{}
$created = $false
$exitCode = 1
$manifest = [ordered]@{
    started_at_utc = [datetime]::UtcNow.ToString("o")
    image = $image
    production_access = $false
    email_delivery = "captured in process; no external mail"
    artifacts = $artifactPath
}

try {
    $arguments = @(
        "run", "--detach", "--rm", "--name", $containerName,
        "--label", "$labelKey=$runId", "--publish", "127.0.0.1::5432",
        "--env", "POSTGRES_USER=nl_test", "--env", "POSTGRES_PASSWORD=local-uat-only",
        "--env", "POSTGRES_DB=nutrilift_auth_test",
        "--tmpfs", "/var/lib/postgresql/data", $image
    )
    & docker @arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not create the isolated PostgreSQL container" }
    $created = $true
    $deadline = [datetime]::UtcNow.AddSeconds(45)
    $ready = $false
    do {
        & docker exec $containerName pg_isready --quiet -U nl_test -d nutrilift_auth_test
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 250
    } while ([datetime]::UtcNow -lt $deadline)
    if (-not $ready) { throw "PostgreSQL did not become ready" }

    $inspection = (& docker inspect $containerName | ConvertFrom-Json)[0]
    $binding = $inspection.NetworkSettings.Ports.'5432/tcp'[0]
    if ($binding.HostIp -ne "127.0.0.1") { throw "Test database must bind to loopback only" }
    $port = [int]$binding.HostPort
    $manifest["image_id"] = $inspection.Image
    $manifest["postgres_version"] = (& docker exec $containerName psql -U nl_test -d nutrilift_auth_test -Atc "SHOW server_version;").Trim()
    $testUrl = "postgresql+psycopg://nl_test:local-uat-only@127.0.0.1:$port/nutrilift_auth_test"
    $overrides = @{
        NUTRILIFT_PG_TEST_URL = $testUrl
        DATABASE_URL = $testUrl
        JWT_SECRET = "postgres-uat-only-not-a-production-secret"
        GEMINI_API_KEY = ""
        RESEND_API_KEY = ""
    }
    foreach ($key in $overrides.Keys) {
        $previousEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, $overrides[$key], "Process")
    }
    Push-Location $backend
    try {
        & $Python -m pytest tests/test_account_lifecycle.py tests/test_postgres_accounts.py tests/test_profile_history.py -m postgres -q -p no:cacheprovider "--junitxml=$junitPath"
        $exitCode = $LASTEXITCODE
    }
    finally { Pop-Location }
    if (Test-Path -LiteralPath $junitPath) {
        [xml]$junit = Get-Content -LiteralPath $junitPath -Raw
        $suite = $junit.testsuites.testsuite
        $manifest["tests"] = [int]$suite.tests
        $manifest["failures"] = [int]$suite.failures
        $manifest["errors"] = [int]$suite.errors
        $manifest["skipped"] = [int]$suite.skipped
    }
}
finally {
    foreach ($key in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previousEnvironment[$key], "Process")
    }
    if ($created) {
        # Only stop the exact container created here, after checking its run label.
        $owned = (& docker inspect $containerName | ConvertFrom-Json)[0]
        if ($owned.Config.Labels.$labelKey -eq $runId) {
            & docker stop --timeout 5 $containerName | Out-Null
            $manifest["container_removed"] = ($LASTEXITCODE -eq 0)
        }
        else { throw "Refusing cleanup: test container label does not match this run" }
    }
    $manifest["finished_at_utc"] = [datetime]::UtcNow.ToString("o")
    $manifest["exit_code"] = $exitCode
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $artifactPath "summary.json") -Encoding UTF8
    Write-Output "PostgreSQL UAT report: $artifactPath"
}
exit $exitCode
