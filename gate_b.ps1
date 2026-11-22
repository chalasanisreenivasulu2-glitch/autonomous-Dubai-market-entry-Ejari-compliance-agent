# gate_b.ps1 - Gate B verification (Tests 1-3)

Write-Host "=========== TEST 1: HEALTH ===========" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod http://127.0.0.1:8000/health
    $health | ConvertTo-Json
} catch {
    Write-Host "HEALTH FAILED: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=========== TEST 2: FULL PIPELINE ===========" -ForegroundColor Cyan

$body = @{
  proposed_name_en = "Veloce Cognitive Systems LLC"
  business_activity = "AI & Enterprise Software"
  origin_country = "India"
  visa_count = 12
  needs_physical_office = $true
  raw_lease_en = "CLAUSE 4 (RENT): AED 240,000.`nCLAUSE 9 (MAINTENANCE): Landlord covers structural > AED 2,500.`nCLAUSE 14 (TERMINATION): 90 days notice."
  raw_lease_ar = "البند 4: 240,000 درهم.`nالبند 9: المستأجر يتحمل كل شيء.`nالبند 14: إخلاء فوري."
  current_rent_aed = 200000
  proposed_rent_aed = 240000
  rera_benchmark_aed = 230000
  notice_days_given = 60
  is_renewal = $true
  trade_name_certificate = "Veloce Cognitive Systems LLC"
  lease_tenant_name = "Veloce Tech Systems Co."
  title_deed_owner = "Al Fajer Commercial Properties LLC"
  lease_landlord_name = "Al Fajer Commercial Properties LLC"
  makani_number = "2849104721"
} | ConvertTo-Json

try {
    $r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/launch/start" -ContentType "application/json" -Body $body
} catch {
    Write-Host "PIPELINE FAILED: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd() -ForegroundColor Red
    }
    exit 1
}

Write-Host "STATUS:       $($r.status)"
Write-Host "STAGE:        $($r.current_stage)"
Write-Host "JURISDICTION: $($r.selected_jurisdiction.jurisdiction_code)"
Write-Host "THREAD_ID:    $($r.thread_id)"
Write-Host ""
Write-Host "--- FINDINGS ---"
$r.lease_findings | Select-Object clause_id, severity, issue_type | Format-Table

$r.thread_id | Set-Content thread_id.txt

Write-Host ""
Write-Host "=========== TEST 3: RESUME + PDF ===========" -ForegroundColor Cyan

$threadId = Get-Content thread_id.txt
Write-Host "Resuming thread: $threadId"

$resume = @{ thread_id = $threadId; approved = $true; reviewer_notes = "Gate B dry-run approval." } | ConvertTo-Json

try {
    $final = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/launch/resume" -ContentType "application/json" -Body $resume
} catch {
    Write-Host "RESUME FAILED: $_" -ForegroundColor Red
    exit 1
}

Write-Host "FINAL STATUS:    $($final.status)"
Write-Host "HUMAN APPROVED:  $($final.human_approved)"
Write-Host "FINAL STAGE:     $($final.current_stage)"

try {
    Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/launch/$threadId/report.pdf" -OutFile "gate_b_report.pdf"
    $size = (Get-Item gate_b_report.pdf).Length
    $header = [System.IO.File]::ReadAllBytes("gate_b_report.pdf")[0..7]
    Write-Host "PDF SIZE:        $size bytes"
    Write-Host "PDF HEADER:      $(($header | ForEach-Object { [char]$_ }) -join '')"
} catch {
    Write-Host "PDF DOWNLOAD FAILED: $_" -ForegroundColor Red
}