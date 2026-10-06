<#
.SYNOPSIS
Executes every measure in the generated Power BI model against a real engine.

.DESCRIPTION
Power BI reports a broken measure as an empty visual, not an error, and a TMDL
syntax slip (an unescaped apostrophe in a measure name) stops Desktop opening
the model at all. Neither shows up until someone opens the file. This script
needs no UI:

1. Deserializes powerbi/project/Corridor.SemanticModel with Desktop's own TOM
   library, which reports TMDL errors with a line number.
2. Deploys it as a scratch database ("CorridorCheck") into the Analysis
   Services engine of a running Power BI Desktop, beside whatever that instance
   has open, and runs a full refresh (the data is embedded M, so no credentials).
3. Executes EVALUATE ROW for every measure and fails on any error.
4. Writes the output of the "HTML ..." measures to -HtmlOut, for
   scripts/preview_powerbi_html.py to render with the report's stylesheet.

Start Power BI Desktop first (an empty instance is fine). Windows only.

.EXAMPLE
pwsh scripts/validate_powerbi_model.ps1
#>
param(
    [int]$Port = 0,
    [string]$HtmlOut = "tmp/powerbi_html_measures.json",
    [switch]$KeepDatabase
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$model = Join-Path $root "powerbi/project/Corridor.SemanticModel/definition"

# WindowsApps cannot be listed without admin rights; the package knows where it lives.
$package = Get-AppxPackage -Name "Microsoft.MicrosoftPowerBIDesktop" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $package) { throw "Power BI Desktop (Store) is not installed." }
$bin = Join-Path $package.InstallLocation "bin"
Add-Type -Path (Join-Path $bin "Microsoft.PowerBI.Tabular.dll")
Add-Type -Path (Join-Path $bin "Microsoft.PowerBI.AdomdClient.dll")

if ($Port -eq 0) {
    # Each running Desktop writes its engine's port into its workspace folder.
    $workspaces = Join-Path $env:USERPROFILE "Microsoft\Power BI Desktop Store App\AnalysisServicesWorkspaces"
    $live = Get-ChildItem $workspaces -Directory | Sort-Object LastWriteTime -Descending | ForEach-Object {
        $file = Join-Path $_.FullName "Data\msmdsrv.port.txt"
        if (Test-Path $file) { [int]([IO.File]::ReadAllText($file, [Text.Encoding]::Unicode).Trim()) }
    } | Where-Object { Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue } | Select-Object -First 1
    if (-not $live) { throw "No running Power BI Desktop engine found. Open Power BI Desktop and retry." }
    $Port = $live
}

$db = [Microsoft.AnalysisServices.Tabular.TmdlSerializer]::DeserializeDatabaseFromFolder($model)
$db.Name = "CorridorCheck"; $db.ID = "CorridorCheck"
$server = New-Object Microsoft.AnalysisServices.Tabular.Server
$server.Connect("Data Source=localhost:$Port")
if ($server.Databases.ContainsName("CorridorCheck")) { $server.Databases.GetByName("CorridorCheck").Drop() }
$server.Databases.Add($db) | Out-Null
$db.Update([Microsoft.AnalysisServices.UpdateOptions]::ExpandFull)
$db.Model.RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Full)
$db.Model.SaveChanges() | Out-Null
$measures = foreach ($table in $db.Model.Tables) { foreach ($m in $table.Measures) { $m.Name } }
Write-Host "deployed to localhost:$Port and refreshed: $($db.Model.Tables.Count) tables, $($measures.Count) measures"

$connection = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Port;Catalog=CorridorCheck")
$connection.Open()
$failures = @(); $html = [ordered]@{}
foreach ($name in $measures) {
    $command = $connection.CreateCommand()
    $command.CommandText = "EVALUATE ROW(""v"", [" + $name.Replace("]", "]]") + "])"
    try {
        $reader = $command.ExecuteReader(); $reader.Read() | Out-Null
        $value = $reader.GetValue(0); $reader.Close()
        if ($name.StartsWith("HTML ")) { $html[$name] = "$value" }
    } catch {
        $failures += "$name : $($_.Exception.Message.Split([Environment]::NewLine)[0])"
    }
}
$connection.Close()
if (-not $KeepDatabase) { $server.Databases.GetByName("CorridorCheck").Drop() }
$server.Disconnect()

$out = Join-Path $root $HtmlOut
New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null
$html | ConvertTo-Json | Out-File -Encoding utf8 $out
if ($failures) {
    Write-Host "$($failures.Count) of $($measures.Count) measures failed:"
    $failures | ForEach-Object { Write-Host "  $_" }
    exit 1
}
Write-Host "all $($measures.Count) measures executed; $($html.Count) HTML panels written to $HtmlOut"
