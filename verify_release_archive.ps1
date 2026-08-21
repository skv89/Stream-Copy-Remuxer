param(
    [string]$Version = "1.4.1"
)

$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$zipPath = [IO.Path]::GetFullPath((Join-Path $projectRoot "Stream-Copy-Remuxer-v$Version-Windows-x64.zip"))
$qaRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "qa\release-v$Version-onefile-final"))
$extractRoot = [IO.Path]::GetFullPath((Join-Path $qaRoot "fresh-zip-extraction"))
$reportPath = [IO.Path]::GetFullPath((Join-Path $qaRoot "zip-integrity.json"))
$extractedRelease = Join-Path $extractRoot "release-stream-copy-remuxer-v$Version"

foreach ($path in @($zipPath, $qaRoot, $extractRoot, $reportPath, $extractedRelease)) {
    $resolved = [IO.Path]::GetFullPath($path)
    if (-not $resolved.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing an operation outside the project root: $resolved"
    }
}
if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
    throw "Release archive is missing: $zipPath"
}
if (Test-Path -LiteralPath $extractRoot) {
    throw "Fresh extraction target already exists and will not be overwritten: $extractRoot"
}
if (Test-Path -LiteralPath $reportPath) {
    throw "Integrity report already exists and will not be overwritten: $reportPath"
}

Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot
$manifestPath = Join-Path $extractedRelease "release_manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "The extracted archive does not contain release_manifest.json."
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$manifestVersionPassed = [string]$manifest.version -eq $Version
$checks = @(
    foreach ($record in $manifest.files) {
        $filePath = [IO.Path]::GetFullPath((Join-Path $extractedRelease $record.path))
        if (-not $filePath.StartsWith($extractedRelease + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            [ordered]@{ path = $record.path; passed = $false; detail = "manifest path escaped release root" }
            continue
        }
        if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
            [ordered]@{ path = $record.path; passed = $false; detail = "missing" }
            continue
        }
        $item = Get-Item -LiteralPath $filePath
        $hash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $passed = $item.Length -eq [long]$record.size_bytes -and $hash -eq [string]$record.sha256
        [ordered]@{
            path = $record.path
            passed = $passed
            size_bytes = $item.Length
            sha256 = $hash
        }
    }
)
$actualFiles = @(Get-ChildItem -LiteralPath $extractedRelease -Recurse -File)
$expectedCount = @($manifest.files).Count + 1
$payload = [ordered]@{
    schema = 1
    application = "Stream Copy Remuxer"
    version = $Version
    passed = $manifestVersionPassed -and (@($checks | Where-Object { -not $_.passed }).Count -eq 0) -and ($actualFiles.Count -eq $expectedCount)
    zip = [ordered]@{
        path = $zipPath
        size_bytes = (Get-Item -LiteralPath $zipPath).Length
        sha256 = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    extracted_release = $extractedRelease
    manifest_file_count = @($manifest.files).Count
    actual_file_count = $actualFiles.Count
    expected_file_count_including_manifest = $expectedCount
    manifest_version_passed = $manifestVersionPassed
    checks = $checks
}
$payload | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $reportPath -Encoding utf8
if (-not $payload.passed) {
    throw "Fresh archive integrity verification failed. See $reportPath"
}
Write-Host "Fresh archive integrity passed: $reportPath"
Write-Host "Extracted release: $extractedRelease"
