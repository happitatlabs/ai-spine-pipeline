[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputPath,

    [Parameter()]
    [ValidateSet('json', 'json+pack', 'binary', 'binary+pack')]
    [string]$ExportMode = 'json+pack'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SpinePath = 'C:\Program Files\Spine\Spine.com'

function Resolve-FullPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        return (Resolve-Path -LiteralPath $Path).ProviderPath
    }

    $executionRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    return [System.IO.Path]::GetFullPath((Join-Path -Path $executionRoot -ChildPath $Path))
}

try {
    if (-not (Test-Path -LiteralPath $SpinePath -PathType Leaf)) {
        throw "Spine CLI not found: $SpinePath"
    }

    if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
        throw "Input .spine file not found: $InputPath"
    }

    $resolvedInputPath = (Resolve-Path -LiteralPath $InputPath).ProviderPath

    if ([System.IO.Path]::GetExtension($resolvedInputPath) -ne '.spine') {
        throw "Input file must use the .spine extension: $resolvedInputPath"
    }

    $resolvedOutputPath = Resolve-FullPath -Path $OutputPath

    if (-not (Test-Path -LiteralPath $resolvedOutputPath -PathType Container)) {
        Write-Host "Creating output directory: $resolvedOutputPath"
        New-Item -ItemType Directory -Path $resolvedOutputPath -Force | Out-Null
    }

    $arguments = @(
        '-i', $resolvedInputPath
        '-o', $resolvedOutputPath
        '-e', $ExportMode
    )

    Write-Host "Spine CLI: $SpinePath"
    Write-Host "Input:     $resolvedInputPath"
    Write-Host "Output:    $resolvedOutputPath"
    Write-Host "Format:    $ExportMode"
    Write-Host 'Running export...'

    & $SpinePath @arguments
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        throw "Spine export failed with exit code $exitCode."
    }

    $jsonFiles = Get-ChildItem -LiteralPath $resolvedOutputPath -Filter '*.json' -File -Recurse
    $skelFiles = Get-ChildItem -LiteralPath $resolvedOutputPath -Filter '*.skel' -File -Recurse
    $atlasFiles = Get-ChildItem -LiteralPath $resolvedOutputPath -Filter '*.atlas' -File -Recurse
    $pngFiles = Get-ChildItem -LiteralPath $resolvedOutputPath -Filter '*.png' -File -Recurse

    if ($ExportMode -like 'json*' -and -not $jsonFiles) {
        throw "Export completed but no .json file was found under $resolvedOutputPath"
    }

    if ($ExportMode -like 'binary*' -and -not $skelFiles) {
        throw "Export completed but no .skel file was found under $resolvedOutputPath"
    }

    if ($ExportMode -like '*+pack') {
        if (-not $atlasFiles) {
            throw "Export completed but no .atlas file was found under $resolvedOutputPath"
        }

        if (-not $pngFiles) {
            throw "Export completed but no .png file was found under $resolvedOutputPath"
        }
    }

    Write-Host 'Export completed successfully.'
    Write-Host 'Generated files:'

    if ($jsonFiles) {
        $jsonFiles.FullName | ForEach-Object { Write-Host "  JSON : $_" }
    }

    if ($skelFiles) {
        $skelFiles.FullName | ForEach-Object { Write-Host "  SKEL : $_" }
    }

    if ($atlasFiles) {
        $atlasFiles.FullName | ForEach-Object { Write-Host "  ATLAS: $_" }
    }

    if ($pngFiles) {
        $pngFiles.FullName | ForEach-Object { Write-Host "  PNG  : $_" }
    }
}
catch {
    Write-Error $_
    exit 1
}
