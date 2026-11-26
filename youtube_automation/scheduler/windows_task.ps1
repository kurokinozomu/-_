# Windows のタスクスケジューラに登録する (PowerShell を管理者で実行)。$Repo を自分のフォルダに変更。
$Repo = "C:\Users\you\-_"
$Py = "$Repo\.venv\Scripts\python.exe"
$jobs = @(
  @{Name="ytops-daily";  Time="06:00"; Args="-m ytops daily"},
  @{Name="ytops-noon";   Time="12:30"; Args="-m ytops daily --no-produce"},
  @{Name="ytops-night";  Time="22:00"; Args="-m ytops daily --no-produce --no-llm"},
  @{Name="ytops-backup"; Time="23:30"; Args="-m ytops backup"}
)
foreach ($j in $jobs) {
  $a = New-ScheduledTaskAction -Execute $Py -Argument $j.Args -WorkingDirectory $Repo
  $t = New-ScheduledTaskTrigger -Daily -At $j.Time
  # スリープからの復帰後に、逃した実行を開始する
  $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 4)
  Register-ScheduledTask -TaskName $j.Name -Action $a -Trigger $t -Settings $s -Force
}
$w = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "23:00"
Register-ScheduledTask -TaskName "ytops-weekly" -Action (New-ScheduledTaskAction -Execute $Py -Argument "-m ytops report --weekly" -WorkingDirectory $Repo) -Trigger $w -Force
