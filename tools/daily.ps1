<#
  Local daily run. Collect, refresh STATUS.md, commit.

  This repository is collected from this machine only; there is no scheduled
  runner. If the machine is off at the usual time the day is simply skipped, so
  check STATUS.md rather than assuming a run happened.
#>
[CmdletBinding()]
param(
    [switch]$NoCommit,
    # Skip the Notion step entirely. Without it the step still runs but reports
    # "skipped" when NOTION_TOKEN / NOTION_DATABASE_ID are absent.
    [switch]$NoNotion,
    # Show what would be written to Notion without contacting it.
    [switch]$DryRunNotion
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $day = (Get-Date).ToString('yyyy-MM-dd')
    $dir = "evidence/$day/daily"
    $cli = 'tools/collect_public_notices.py'

    python3 $cli validate
    if ($LASTEXITCODE -ne 0) { throw 'source registry is invalid' }

    python3 $cli collect --source all --out $dir
    $collectFailed = $LASTEXITCODE -ne 0

    python3 $cli status --current $dir --out STATUS.md
    if ($LASTEXITCODE -ne 0) { throw 'could not write STATUS.md' }

    # Notion is the review surface; STATUS.md is the read-only mirror. The sync
    # only ever creates a new row or refreshes a deadline - it never writes back
    # over a review.
    if (-not $NoNotion) {
        if ($DryRunNotion) {
            python3 $cli notion --current $dir --dry-run
        } else {
            python3 $cli notion --current $dir
        }
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Notion sync did not complete' }
    }

    if (-not $NoCommit) {
        git add -A
        git diff --cached --quiet
        if ($LASTEXITCODE -ne 0) {
            $note = if ($collectFailed) { ' (partial: a source did not answer)' } else { '' }
            git commit -q -m "chore: daily radar $day$note"
        }
    }

    if ($collectFailed) {
        Write-Warning 'At least one source did not answer. STATUS.md marks the run partial.'
        exit 1
    }
}
finally {
    Pop-Location
}
