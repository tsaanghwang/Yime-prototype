param(
    [ValidateSet("full", "variable", "shorthand")]
    [string]$Mode = "variable",

    [ValidateSet("layout-key", "runtime-symbol")]
    [string]$CodeForm = "layout-key",

    [string]$RepoRoot = "",
    [string]$OutputDir = "",
    [string]$RimeUserDir = "",
    [string]$WeaselRoot = "C:\dev\weasel",
    [string]$RimeDeployer = "",
    [string]$SharedDataDir = "",

    [switch]$SkipExport,
    [switch]$SkipSwitcherConfig,
    [switch]$NoBackup,
    [switch]$NoDeploy,
    [switch]$RegisterWeasel,
    [switch]$StartWeaselServer
)

$ErrorActionPreference = "Stop"

function Resolve-RequiredPath {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Text
    )

    $encoding = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Backup-IfNeeded {
    param([string]$Path)

    if ($NoBackup -or -not (Test-Path -LiteralPath $Path)) {
        return
    }

    $timestamp = Get-Date -Format "yyyyMMddHHmmss"
    Copy-Item -LiteralPath $Path -Destination "$Path.yime-bak-$timestamp" -Force
}

function Find-FirstExistingPath {
    param([string[]]$Candidates)

    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return ""
}

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
else {
    $RepoRoot = Resolve-RequiredPath -Path $RepoRoot -Label "Repo root"
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot ".generated\rime"
}
if (-not $RimeUserDir) {
    $RimeUserDir = Join-Path $env:APPDATA "Rime"
}

$schemaId = "yime_$Mode"
$exporter = Resolve-RequiredPath -Path (Join-Path $RepoRoot "yime\export_rime_yime.py") -Label "Rime exporter"

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
New-Item -ItemType Directory -Path $RimeUserDir -Force | Out-Null

if (-not $SkipExport) {
    Push-Location $RepoRoot
    try {
        & python $exporter --mode $Mode --code-form $CodeForm --output-dir $OutputDir
        if ($LASTEXITCODE -ne 0) {
            throw "Rime export failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

$schemaFile = Resolve-RequiredPath -Path (Join-Path $OutputDir "$schemaId.schema.yaml") -Label "Generated schema"
$dictFile = Resolve-RequiredPath -Path (Join-Path $OutputDir "$schemaId.dict.yaml") -Label "Generated dict"

Copy-Item -LiteralPath $schemaFile -Destination (Join-Path $RimeUserDir "$schemaId.schema.yaml") -Force
Copy-Item -LiteralPath $dictFile -Destination (Join-Path $RimeUserDir "$schemaId.dict.yaml") -Force

if (-not $SkipSwitcherConfig) {
    $defaultCustom = Join-Path $RimeUserDir "default.custom.yaml"
    $userYaml = Join-Path $RimeUserDir "user.yaml"

    Backup-IfNeeded -Path $defaultCustom
    Backup-IfNeeded -Path $userYaml

    Write-Utf8NoBom -Path $defaultCustom -Text @"
patch:
  schema_list:
    - schema: $schemaId
"@

    Write-Utf8NoBom -Path $userYaml -Text @"
var:
  previously_selected_schema: $schemaId
"@
}

if (-not $RimeDeployer) {
    $RimeDeployer = Find-FirstExistingPath @(
        (Join-Path $WeaselRoot "librime\build_x64\bin\Release\rime_deployer.exe"),
        (Join-Path $WeaselRoot "librime\dist_x64\bin\rime_deployer.exe"),
        (Join-Path $WeaselRoot "output\rime_deployer.exe"),
        "C:\dev\librime\build\bin\Release\rime_deployer.exe"
    )
}
$RimeDeployer = Resolve-RequiredPath -Path $RimeDeployer -Label "rime_deployer.exe"

if (-not $SharedDataDir) {
    $SharedDataDir = Find-FirstExistingPath @(
        (Join-Path $WeaselRoot "output\data"),
        (Join-Path $WeaselRoot "librime\data\minimal"),
        "C:\dev\librime\data\minimal"
    )
}
$SharedDataDir = Resolve-RequiredPath -Path $SharedDataDir -Label "Rime shared data"

if (-not $NoDeploy) {
    $buildDir = Join-Path $RimeUserDir "build"
    New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
    & $RimeDeployer --build $RimeUserDir $SharedDataDir $buildDir
    if ($LASTEXITCODE -ne 0) {
        throw "rime_deployer failed with exit code $LASTEXITCODE"
    }
}

if ($RegisterWeasel) {
    $setupExe = Resolve-RequiredPath -Path (Join-Path $WeaselRoot "output\WeaselSetup.exe") -Label "WeaselSetup.exe"
    & $setupExe /s
    if ($LASTEXITCODE -ne 0) {
        throw "WeaselSetup failed with exit code $LASTEXITCODE"
    }
}

if ($StartWeaselServer) {
    $serverExe = Resolve-RequiredPath -Path (Join-Path $WeaselRoot "output\WeaselServer.exe") -Label "WeaselServer.exe"
    Start-Process -FilePath $serverExe -WindowStyle Hidden
}

Write-Host "Yime Rime schema deployed."
Write-Host "  schema:      $schemaId"
Write-Host "  user dir:    $RimeUserDir"
Write-Host "  shared data: $SharedDataDir"
Write-Host "  deployer:    $RimeDeployer"
