$ErrorActionPreference = "Stop"

$scriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Join-Path (Get-Location) "scripts" }
$repo = Split-Path -Parent $scriptRoot
Set-Location $repo

$env:PYTHONPATH = (Resolve-Path ".\.venv\Lib\site-packages").Path
$python = Join-Path $repo ".venv\Scripts\python.exe"
$humanDir = Join-Path $repo "00_项目成果总览_先看这里\02_OCR结果_13本扫描PDF"
$outRoot = "data_pipeline\ocr_layout_aware_tesseract_night_corrected\tsinghua_gas_turbine_books"
$fullOutRoot = Join-Path $repo $outRoot
$logDir = Join-Path $repo "observability\logs\ocr_night_correction"
$consoleLog = Join-Path $logDir "ocr_night_task_20260518.console.log"
$doneFile = Join-Path $humanDir "00_明早先看_夜间OCR总检结果.md"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $humanDir | Out-Null

function Run-Step {
    param(
        [string]$Name,
        [scriptblock]$Block
    )
    $start = Get-Date
    "[$($start.ToString('s'))] START $Name" | Tee-Object -FilePath $consoleLog -Append
    & $Block 2>&1 | Tee-Object -FilePath $consoleLog -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Name, exit=$LASTEXITCODE"
    }
    $end = Get-Date
    "[$($end.ToString('s'))] DONE $Name, elapsed=$([math]::Round(($end-$start).TotalMinutes,2))min" | Tee-Object -FilePath $consoleLog -Append
}

try {
    Run-Step "night multi-strategy correction" {
        & $python -S "scripts\ocr_night_correction.py" `
            --input-root "data_pipeline\ocr_layout_aware_tesseract_highres_refined_pass2\tsinghua_gas_turbine_books" `
            --output-root $outRoot `
            --workers 6 `
            --report-stem "ocr_night_correction_20260518" `
            --resume `
            --copy-to-human-dir
    }

    Run-Step "quality audit" {
        & $python -S "scripts\audit_ocr_quality.py" `
            --output-root $outRoot `
            --report-stem "ocr_night_corrected_quality_audit_20260518" `
            --title "夜间总检矫正版 OCR 交付前质量审计" `
            --copy-to-human-dir
    }

    Run-Step "delivery acceptance" {
        & $python -S "scripts\generate_ocr_delivery_acceptance.py" `
            --output-root $outRoot `
            --report-stem "ocr_night_corrected_delivery_acceptance_20260518" `
            --copy-to-human-dir
    }

    Run-Step "spotcheck pack" {
        & $python -S "scripts\build_ocr_spotcheck_pack.py" `
            --acceptance-json "data_pipeline\reports\ocr_night_corrected_delivery_acceptance_20260518.json" `
            --ocr-root $outRoot `
            --out-dir "00_项目成果总览_先看这里\02_OCR结果_13本扫描PDF\OCR人工抽检样本包_夜间总检矫正版" `
            --title "夜间总检矫正版 OCR 人工抽检样本包" `
            --max-per-doc 2 `
            --render-scale 0.7
    }

    $finalLink = Join-Path $humanDir "最终OCR文本_真实文件夹"
    if (Test-Path -LiteralPath $finalLink) {
        $item = Get-Item -LiteralPath $finalLink -Force
        if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing to remove non-junction path: $finalLink"
        }
        [System.IO.Directory]::Delete($finalLink)
    }
    New-Item -ItemType Junction -Path $finalLink -Target $fullOutRoot | Out-Null

    $legacyLink = Join-Path $humanDir "高分辨率修正版_OCR文本_真实文件夹"
    if (Test-Path -LiteralPath $legacyLink) {
        $item = Get-Item -LiteralPath $legacyLink -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            [System.IO.Directory]::Delete($legacyLink)
            New-Item -ItemType Junction -Path $legacyLink -Target $fullOutRoot | Out-Null
        }
    }

    $night = Get-Content -Raw -Encoding UTF8 "data_pipeline\reports\ocr_night_correction_20260518.json" | ConvertFrom-Json
    $accept = Get-Content -Raw -Encoding UTF8 "data_pipeline\reports\ocr_night_corrected_delivery_acceptance_20260518.json" | ConvertFrom-Json
    $readme = @"
# 明早先看：夜间 OCR 总检结果

生成时间：$(Get-Date -Format s)

## 做了什么

- 对风险页做了夜间多策略 OCR 总检矫正。
- 覆盖低置信、无文字、极短文本、疑似断句、版面顺序风险页。
- 每页尝试多个 OCR 策略，只在综合质量分明显更好时替换。

## 数字结果

- 总页数：$($accept.pages_done) / $($accept.total_pages)
- 有文字页：$($accept.pages_with_text)
- 完整性错误：$($accept.validation_errors.Count)
- 夜间目标风险页：$($night.target_pages)
- 夜间已尝试页：$($night.attempted_pages)
- 夜间接受替换页：$($night.accepted_pages)
- 最终低置信页：$($accept.risk_counts.'平均置信度偏低')
- 最终无文字页：$($accept.risk_counts.'无文字')

## 直接打开

- `最终OCR文本_真实文件夹`
- `OCR交付前验收报告.md`
- `OCR交付风险页清单.csv`
- `04_夜间总检矫正/OCR夜间总检矫正报告.md`
- `OCR人工抽检样本包_夜间总检矫正版/OCR人工抽检样本.html`

## 交付口径

可以说：已完成全量 OCR、两轮高清重识别和夜间多策略总检矫正。

不能说：OCR 逐字完全正确。剩余低置信页、公式表格页、两栏复杂页仍需人工复核。
"@
    Set-Content -LiteralPath $doneFile -Encoding UTF8 -Value $readme

    $readmePath = Join-Path $humanDir "README.md"
    Set-Content -LiteralPath $readmePath -Encoding UTF8 -Value $readme

    "[DONE] OCR night task completed at $(Get-Date -Format s)" | Tee-Object -FilePath $consoleLog -Append
} catch {
    "[FAILED] $($_.Exception.Message)" | Tee-Object -FilePath $consoleLog -Append
    throw
}
