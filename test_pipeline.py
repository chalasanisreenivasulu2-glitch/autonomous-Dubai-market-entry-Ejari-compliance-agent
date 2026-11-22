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

$r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/launch/start" -ContentType "application/json" -Body $body

Write-Host "STATUS:       $($r.status)"
Write-Host "STAGE:        $($r.current_stage)"
Write-Host "JURISDICTION: $($r.selected_jurisdiction.jurisdiction_code)"
Write-Host "THREAD_ID:    $($r.thread_id)"
Write-Host ""
Write-Host "--- FINDINGS ---"
$r.lease_findings | Select-Object clause_id, severity, issue_type | Format-Table

# Save thread_id for Test 3
$r.thread_id | Set-Content thread_id.txt