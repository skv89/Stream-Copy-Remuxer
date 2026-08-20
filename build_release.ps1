param(
    [string]$Version = "1.3.2"
)

$ErrorActionPreference = "Stop"
$env:PYTHONNOUSERSITE = "1"
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$buildPython = [IO.Path]::GetFullPath("C:\Users\Doug\Documents\ChatGPT\Video corrections\work\pyinstaller311-env\Scripts\python.exe")
$workRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "work\stream-copy-remuxer-v$Version-build13-onefile"))
$env:PYTHONUSERBASE = [IO.Path]::GetFullPath((Join-Path $workRoot "python-userbase"))
$buildRoot = [IO.Path]::GetFullPath((Join-Path $workRoot "pyinstaller-build"))
$distRoot = [IO.Path]::GetFullPath((Join-Path $workRoot "pyinstaller-dist"))
$specRoot = [IO.Path]::GetFullPath((Join-Path $workRoot "pyinstaller-spec"))
$candidateRoot = [IO.Path]::GetFullPath((Join-Path $workRoot "candidate-release"))
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "release-stream-copy-remuxer-v$Version"))
$zipPath = [IO.Path]::GetFullPath((Join-Path $projectRoot "Stream-Copy-Remuxer-v$Version-Windows-x64.zip"))
$qaRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "qa\release-v$Version-onefile-final"))

function Assert-SafeProjectChild([string]$Path) {
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing an operation outside the project root: $resolved"
    }
}

function Assert-SafeWorkChild([string]$Path) {
    $resolved = [IO.Path]::GetFullPath($Path)
    $isWorkRoot = $resolved.Equals($workRoot, [StringComparison]::OrdinalIgnoreCase)
    $isChild = $resolved.StartsWith($workRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
    if (-not ($isWorkRoot -or $isChild)) {
        throw "Refusing to clean a path outside this build's work folder: $resolved"
    }
}

foreach ($path in @($workRoot, $buildRoot, $distRoot, $specRoot, $candidateRoot, $releaseRoot, $zipPath, $qaRoot)) {
    Assert-SafeProjectChild $path
}

if (-not (Test-Path -LiteralPath $buildPython -PathType Leaf)) {
    throw "The verified Python/PyInstaller build runtime was not found: $buildPython"
}
& $buildPython -c "import importlib.metadata as m; assert m.version('PyInstaller') == '6.16.0'"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 6.16.0 is required in the selected build runtime."
}
& $buildPython -c "import importlib.metadata as m; assert m.version('tkinterdnd2') == '0.6.2'"
if ($LASTEXITCODE -ne 0) {
    throw "tkinterdnd2 0.6.2 is required in the selected build runtime."
}
if (Test-Path -LiteralPath $releaseRoot) {
    throw "Release path already exists and will not be overwritten: $releaseRoot"
}
if (Test-Path -LiteralPath $zipPath) {
    throw "Release archive already exists and will not be overwritten: $zipPath"
}
if (Test-Path -LiteralPath $qaRoot) {
    throw "QA path already exists and will not be overwritten: $qaRoot"
}

if (Test-Path -LiteralPath $workRoot) {
    Assert-SafeWorkChild $workRoot
    Remove-Item -LiteralPath $workRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $buildRoot, $distRoot, $specRoot -Force | Out-Null

& $buildPython -s -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "Stream Copy Remuxer" `
    --distpath $distRoot `
    --workpath $buildRoot `
    --specpath $specRoot `
    (Join-Path $projectRoot "remux_main.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$builtExe = Join-Path $distRoot "Stream Copy Remuxer.exe"
Assert-SafeWorkChild $builtExe
if (-not (Test-Path -LiteralPath $builtExe -PathType Leaf)) {
    throw "PyInstaller did not create the expected standalone executable: $builtExe"
}

New-Item -ItemType Directory -Path $candidateRoot | Out-Null
Move-Item -LiteralPath $builtExe -Destination (Join-Path $candidateRoot "Stream Copy Remuxer.exe")
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $candidateRoot
Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md") -Destination $candidateRoot

$licenses = Join-Path $candidateRoot "licenses"
New-Item -ItemType Directory -Path $licenses | Out-Null
Copy-Item -LiteralPath "C:\Program Files\Python311\LICENSE.txt" -Destination (Join-Path $licenses "Python-3.11-LICENSE.txt")
Copy-Item -LiteralPath "C:\Program Files\Python311\tcl\tk8.6\license.terms" -Destination (Join-Path $licenses "Tcl-Tk-license.terms")
Copy-Item -LiteralPath "C:\Users\Doug\Documents\ChatGPT\Video corrections\work\pyinstaller311-env\Lib\site-packages\pyinstaller-6.16.0.dist-info\licenses\COPYING.txt" -Destination (Join-Path $licenses "PyInstaller-COPYING.txt")
Copy-Item -LiteralPath "C:\Users\Doug\Documents\ChatGPT\Video corrections\work\pyinstaller311-env\Lib\site-packages\tkinterdnd2-0.6.2.dist-info\licenses\LICENSE" -Destination (Join-Path $licenses "TkinterDnD2-MIT-LICENSE.txt")

New-Item -ItemType Directory -Path $qaRoot | Out-Null
$packagedSelfTest = Join-Path $qaRoot "packaged-self-test.json"
$packagedSelfTestRelative = [IO.Path]::GetRelativePath($projectRoot, $packagedSelfTest)
$selfTestProcess = Start-Process `
    -FilePath (Join-Path $candidateRoot "Stream Copy Remuxer.exe") `
    -ArgumentList @("--self-test", "--output", $packagedSelfTestRelative) `
    -WorkingDirectory $projectRoot `
    -Wait `
    -PassThru `
    -WindowStyle Hidden
if ($selfTestProcess.ExitCode -ne 0) {
    throw "The packaged executable self-test failed with exit code $($selfTestProcess.ExitCode)."
}
if (-not (Test-Path -LiteralPath $packagedSelfTest -PathType Leaf)) {
    throw "The packaged executable did not write its self-test report."
}
$selfTestPayload = Get-Content -LiteralPath $packagedSelfTest -Raw | ConvertFrom-Json
if (-not $selfTestPayload.passed) {
    throw "The packaged executable self-test report did not pass."
}
if ([string]$selfTestPayload.version -ne $Version) {
    throw "The packaged executable reports version $($selfTestPayload.version), expected $Version."
}
if (-not $selfTestPayload.observations.gui.checks.drag_drop_registered) {
    throw "The packaged executable did not register TkDND drag-and-drop."
}
if ([string]::IsNullOrWhiteSpace([string]$selfTestPayload.observations.gui.observations.tkdnd_version)) {
    throw "The packaged executable did not report a TkDND runtime version."
}
if (-not $selfTestPayload.observations.layout_scaling.passed) {
    throw "The packaged executable did not pass the 100/150/200 percent DPI layout audit."
}
if (-not $selfTestPayload.observations.gui.checks.destination_control_present) {
    throw "The packaged executable did not expose the optional batch destination controls."
}
if (-not $selfTestPayload.observations.gui.checks.custom_destination_applies_to_all_rows) {
    throw "The packaged executable did not pass common-destination output planning."
}
if (-not $selfTestPayload.observations.gui.checks.clear_destination_restores_source_folders) {
    throw "The packaged executable did not restore beside-source planning after clearing the destination."
}
if (-not $selfTestPayload.observations.gui.checks.status_column_user_resizable) {
    throw "The packaged executable did not expose a stretchable Status column."
}
if (-not $selfTestPayload.observations.gui.checks.details_log_ten_rows) {
    throw "The packaged executable did not expose the requested 10-row Details log."
}
if (-not $selfTestPayload.observations.gui.checks.compatible_confirmation_discloses_omissions) {
    throw "The packaged executable did not disclose compatible-mode omissions in confirmation text."
}
if (-not $selfTestPayload.observations.gui.checks.video_only_confirmation_discloses_audio_omissions) {
    throw "The packaged executable did not disclose video-only audio omissions in confirmation text."
}
if (-not $selfTestPayload.checks.bounded_input_analysis_before_source) {
    throw "The packaged executable did not apply the bounded input-analysis option before the source."
}
if (-not $selfTestPayload.checks.compatible_plan_omits_only_subrip) {
    throw "The packaged executable did not select the safe compatible-stream set."
}
if (-not $selfTestPayload.checks.strict_subrip_mp4_blocked_before_ffmpeg) {
    throw "The packaged executable did not block a strict SubRip/MP4 plan before FFmpeg."
}
if (-not $selfTestPayload.checks.compatible_command_explicitly_maps_only_video_audio) {
    throw "The packaged executable did not map the compatible FFV1/AAC stream indexes explicitly."
}
if (-not $selfTestPayload.checks.compatible_report_discloses_omitted_subrip) {
    throw "The packaged executable did not disclose the omitted SubRip stream in its audit report."
}
if (-not $selfTestPayload.checks.video_only_plan_selects_video_and_omits_audio_subrip) {
    throw "The packaged executable did not select only video in video-only mode."
}
if (-not $selfTestPayload.checks.video_only_command_maps_no_audio) {
    throw "The packaged executable mapped audio in video-only mode."
}
if (-not $selfTestPayload.checks.video_only_stream_copy_command) {
    throw "The packaged executable did not use stream copy in video-only mode."
}
if (-not $selfTestPayload.checks.video_only_output_has_only_ffv1_video) {
    throw "The packaged executable video-only output retained a non-video stream or changed FFV1."
}
if (-not $selfTestPayload.checks.video_only_report_discloses_audio_and_subrip_omissions) {
    throw "The packaged executable did not disclose video-only audio/SubRip omissions in its audit report."
}

$warningSource = Join-Path $buildRoot "Stream Copy Remuxer\warn-Stream Copy Remuxer.txt"
if (Test-Path -LiteralPath $warningSource -PathType Leaf) {
    Copy-Item -LiteralPath $warningSource -Destination (Join-Path $qaRoot "pyinstaller-warnings.txt")
}

$manifestFiles = Get-ChildItem -LiteralPath $candidateRoot -Recurse -File | Sort-Object FullName
$manifest = [ordered]@{
    schema = 1
    application = "Stream Copy Remuxer"
    version = $Version
    built_utc = [DateTime]::UtcNow.ToString("o")
    packaged_self_test = "passed"
    ffmpeg_bundled = $false
    ffmpeg_installer_enabled = $true
    drag_drop_backend = "TkinterDnD2/TkDND OLE2"
    optional_batch_destination = $true
    output_folder_opener = "Windows shell startfile"
    input_analyze_duration_microseconds = 10000000
    stream_modes = @("av", "video", "compatible", "all")
    compatible_mode_mp4_mov_safe_subtitle_codecs = @("mov_text")
    details_log_rows = 10
    files = @(
        foreach ($file in $manifestFiles) {
            [ordered]@{
                path = [IO.Path]::GetRelativePath($candidateRoot, $file.FullName)
                size_bytes = $file.Length
                sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    )
}
$manifestPath = Join-Path $candidateRoot "release_manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8

Move-Item -LiteralPath $candidateRoot -Destination $releaseRoot
Compress-Archive -LiteralPath $releaseRoot -DestinationPath $zipPath -CompressionLevel Optimal
if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
    throw "The release archive was not created."
}

Write-Host "Built and self-tested standalone release: $releaseRoot"
Write-Host "Archive: $zipPath"
Write-Host "QA: $qaRoot"
