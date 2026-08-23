# Run pytest in a unique project-controlled temporary directory.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$tempRoot = Join-Path $projectRoot ".test-tmp"
$runDirectory = Join-Path $tempRoot ([Guid]::NewGuid().ToString("N"))
$pytestExitCode = 1

try {
    New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
    & python -m pytest -q -p no:cacheprovider --basetemp $runDirectory @args
    $pytestExitCode = $LASTEXITCODE
}
finally {
    try {
        if (Test-Path -LiteralPath $runDirectory) {
            Remove-Item -LiteralPath $runDirectory -Recurse -Force -ErrorAction Stop
        }
    }
    catch {
        Write-Warning ("No se pudo limpiar el directorio temporal de pytest: " + $_.Exception.Message)
    }
}

exit $pytestExitCode
