param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

function Clean-WordCellText {
    param([AllowEmptyString()][string]$Value)

    if ($null -eq $Value) {
        return ""
    }
    $Value = $Value -replace "`r`a$", ""
    $Value = $Value -replace "`a$", ""
    $Value = $Value -replace "`v", "`n"
    $Value = $Value -replace "`r", "`n"
    return $Value.Trim()
}

$source = (Resolve-Path -LiteralPath $SourcePath).Path
$output = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = [System.IO.Path]::GetDirectoryName($output)
if ($outputDirectory) {
    [System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
}

$word = $null
$document = $null
$table = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $document = $word.Documents.Open($source, $false, $true, $false)
    if ($document.Tables.Count -ne 1) {
        throw "Expected exactly one comparison table, found $($document.Tables.Count)."
    }

    $table = $document.Tables.Item(1)
    if ($table.Columns.Count -ne 2) {
        throw "Expected a two-column comparison table, found $($table.Columns.Count) columns."
    }

    $prefixRange = $document.Range(0, $table.Range.Start)
    $instructions = Clean-WordCellText $prefixRange.Text
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($prefixRange)

    $rows = New-Object System.Collections.Generic.List[object]
    for ($rowNumber = 1; $rowNumber -le $table.Rows.Count; $rowNumber++) {
        $leftCell = $null
        $rightCell = $null
        try {
            $leftCell = $table.Cell($rowNumber, 1)
            $rightCell = $table.Cell($rowNumber, 2)
            $pageNumber = [int]$leftCell.Range.Information(3)
            $rows.Add([PSCustomObject]@{
                source_row = $rowNumber
                word_page_number = $pageNumber
                old_text = Clean-WordCellText $leftCell.Range.Text
                proposed_text = Clean-WordCellText $rightCell.Range.Text
            })
        }
        finally {
            if ($rightCell) {
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($rightCell)
            }
            if ($leftCell) {
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($leftCell)
            }
        }
    }

    $payload = [PSCustomObject]@{
        extraction_method = "word-com-read-only-table"
        extraction_version = 1
        source_path = $source
        title = "Putonghua Yiduci Shenyinbiao (2016 draft)"
        proposal_date = "2016-05"
        page_count = [int]$document.ComputeStatistics(2)
        table_count = [int]$document.Tables.Count
        table_row_count = [int]$table.Rows.Count
        table_column_count = [int]$table.Columns.Count
        instructions_text = $instructions
        rows = $rows
    }
    $json = $payload | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText(
        $output,
        $json,
        [System.Text.UTF8Encoding]::new($false)
    )
}
finally {
    if ($table) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($table)
    }
    if ($document) {
        $document.Close($false)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if ($word) {
        $word.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
