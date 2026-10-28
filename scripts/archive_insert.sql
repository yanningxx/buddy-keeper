-- 归档迁移 DML（package + 6 tasks）
-- 由 generate_archive_migration.py 生成，package_name 唯一，重跑同包幂等跳过

INSERT INTO archived_task_packages (package_name, source_machine, operator, zip_storage_key, zip_size_bytes, note)
SELECT 'buddy-keeper-archive-2026-10-27', 'PC-20260923QRMI', '徐', 'archives/buddy-keeper-2026-10-27/workbuddy-old-20261012.zip', 182792, '2026-10-27 本地注销 6 条 Windows 自动签到/旅行计划任务后的归档迁移' 
WHERE NOT EXISTS (SELECT 1 FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27');

INSERT INTO archived_scheduled_tasks (package_id, task_name, description, trigger_type, trigger_detail, principal_user, logon_type, action_command, action_args, working_directory, enabled, settings_json, raw_xml)
SELECT (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27'), 'BuddyTravelBoot', NULL, 'BootTrigger', '{"Delay": "PT1M"}'::jsonb, 'S-1-5-21-2080283827-557422376-331876023-500', 'InteractiveToken', 'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe', '"D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation\buddy_daily.py" run --trigger boot', 'D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation', true, '{"DisallowStartIfOnBatteries": "false", "StopIfGoingOnBatteries": "false", "ExecutionTimeLimit": "PT30M", "MultipleInstancesPolicy": "IgnoreNew", "StartWhenAvailable": "true", "IdleSettings": {"Duration": "PT10M", "WaitTimeout": "PT1H", "StopOnIdleEnd": "true", "RestartOnIdle": "false"}, "UseUnifiedSchedulingEngine": "true"}'::jsonb, '<?xml version="1.0" encoding="UTF-16"?>

<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">

  <RegistrationInfo>

    <URI>\BuddyTravelBoot</URI>

  </RegistrationInfo>

  <Principals>

    <Principal id="Author">

      <UserId>S-1-5-21-2080283827-557422376-331876023-500</UserId>

      <LogonType>InteractiveToken</LogonType>

    </Principal>

  </Principals>

  <Settings>

    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>

    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>

    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>

    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>

    <StartWhenAvailable>true</StartWhenAvailable>

    <IdleSettings>

      <Duration>PT10M</Duration>

      <WaitTimeout>PT1H</WaitTimeout>

      <StopOnIdleEnd>true</StopOnIdleEnd>

      <RestartOnIdle>false</RestartOnIdle>

    </IdleSettings>

    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>

  </Settings>

  <Triggers>

    <BootTrigger>

      <Delay>PT1M</Delay>

    </BootTrigger>

  </Triggers>

  <Actions Context="Author">

    <Exec>

      <Command>C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe</Command>

      <Arguments>"D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation\buddy_daily.py" run --trigger boot</Arguments>

      <WorkingDirectory>D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation</WorkingDirectory>

    </Exec>

  </Actions>

</Task>
' WHERE NOT EXISTS (SELECT 1 FROM archived_scheduled_tasks t WHERE t.package_id = (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27') AND t.task_name = 'BuddyTravelBoot')
UNION ALL
SELECT (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27'), 'BuddyTravelDaily', NULL, 'CalendarTrigger', '{"StartBoundary": "2026-10-15T09:00:00+08:00", "ScheduleByDay": {"DaysInterval": "1"}}'::jsonb, 'S-1-5-21-2080283827-557422376-331876023-500', 'InteractiveToken', 'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe', '"D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation\buddy_daily.py" run --trigger daily', 'D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation', true, '{"DisallowStartIfOnBatteries": "false", "StopIfGoingOnBatteries": "false", "ExecutionTimeLimit": "PT30M", "MultipleInstancesPolicy": "IgnoreNew", "StartWhenAvailable": "true", "IdleSettings": {"Duration": "PT10M", "WaitTimeout": "PT1H", "StopOnIdleEnd": "true", "RestartOnIdle": "false"}, "UseUnifiedSchedulingEngine": "true"}'::jsonb, '<?xml version="1.0" encoding="UTF-16"?>

<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">

  <RegistrationInfo>

    <URI>\BuddyTravelDaily</URI>

  </RegistrationInfo>

  <Principals>

    <Principal id="Author">

      <UserId>S-1-5-21-2080283827-557422376-331876023-500</UserId>

      <LogonType>InteractiveToken</LogonType>

    </Principal>

  </Principals>

  <Settings>

    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>

    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>

    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>

    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>

    <StartWhenAvailable>true</StartWhenAvailable>

    <IdleSettings>

      <Duration>PT10M</Duration>

      <WaitTimeout>PT1H</WaitTimeout>

      <StopOnIdleEnd>true</StopOnIdleEnd>

      <RestartOnIdle>false</RestartOnIdle>

    </IdleSettings>

    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>

  </Settings>

  <Triggers>

    <CalendarTrigger>

      <StartBoundary>2026-10-15T09:00:00+08:00</StartBoundary>

      <ScheduleByDay>

        <DaysInterval>1</DaysInterval>

      </ScheduleByDay>

    </CalendarTrigger>

  </Triggers>

  <Actions Context="Author">

    <Exec>

      <Command>C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe</Command>

      <Arguments>"D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation\buddy_daily.py" run --trigger daily</Arguments>

      <WorkingDirectory>D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation</WorkingDirectory>

    </Exec>

  </Actions>

</Task>
' WHERE NOT EXISTS (SELECT 1 FROM archived_scheduled_tasks t WHERE t.package_id = (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27') AND t.task_name = 'BuddyTravelDaily')
UNION ALL
SELECT (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27'), 'BuddyTravelNetwork', NULL, 'EventTrigger', '{"Subscription": "<QueryList><Query Id=\"0\" Path=\"Microsoft-Windows-NetworkProfile/Operational\"><Select Path=\"Microsoft-Windows-NetworkProfile/Operational\">*[System[Provider[@Name=''Microsoft-Windows-NetworkProfile''] and EventID=10000]]</Select></Query></QueryList>"}'::jsonb, 'S-1-5-21-2080283827-557422376-331876023-500', 'InteractiveToken', 'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe', '"D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation\buddy_daily.py" run --trigger network', 'D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation', true, '{"DisallowStartIfOnBatteries": "false", "StopIfGoingOnBatteries": "false", "ExecutionTimeLimit": "PT30M", "MultipleInstancesPolicy": "IgnoreNew", "StartWhenAvailable": "true", "IdleSettings": {"Duration": "PT10M", "WaitTimeout": "PT1H", "StopOnIdleEnd": "true", "RestartOnIdle": "false"}, "UseUnifiedSchedulingEngine": "true"}'::jsonb, '<?xml version="1.0" encoding="UTF-16"?>

<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">

  <RegistrationInfo>

    <URI>\BuddyTravelNetwork</URI>

  </RegistrationInfo>

  <Principals>

    <Principal id="Author">

      <UserId>S-1-5-21-2080283827-557422376-331876023-500</UserId>

      <LogonType>InteractiveToken</LogonType>

    </Principal>

  </Principals>

  <Settings>

    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>

    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>

    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>

    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>

    <StartWhenAvailable>true</StartWhenAvailable>

    <IdleSettings>

      <Duration>PT10M</Duration>

      <WaitTimeout>PT1H</WaitTimeout>

      <StopOnIdleEnd>true</StopOnIdleEnd>

      <RestartOnIdle>false</RestartOnIdle>

    </IdleSettings>

    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>

  </Settings>

  <Triggers>

    <EventTrigger>

      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="Microsoft-Windows-NetworkProfile/Operational"&gt;&lt;Select Path="Microsoft-Windows-NetworkProfile/Operational"&gt;*[System[Provider[@Name=''Microsoft-Windows-NetworkProfile''] and EventID=10000]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>

    </EventTrigger>

  </Triggers>

  <Actions Context="Author">

    <Exec>

      <Command>C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe</Command>

      <Arguments>"D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation\buddy_daily.py" run --trigger network</Arguments>

      <WorkingDirectory>D:\Workduddy\2026-10-15-10-59-04\buddy-travel-automation</WorkingDirectory>

    </Exec>

  </Actions>

</Task>
' WHERE NOT EXISTS (SELECT 1 FROM archived_scheduled_tasks t WHERE t.package_id = (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27') AND t.task_name = 'BuddyTravelNetwork')
UNION ALL
SELECT (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27'), 'WorkBuddyBootCheckin', 'WorkBuddy boot check-in: silent, console-free, no window', 'LogonTrigger', '{"Delay": "PT30S", "UserId": "PC-20260923QRMI\\Administrator"}'::jsonb, 'S-1-5-21-2080283827-557422376-331876023-500', 'InteractiveToken', 'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe', '"C:\Users\Administrator\WorkBuddy\WorkBuddy\2026-10-12-08-53-54\boot_network_checkin.py"', 'C:\Users\Administrator\WorkBuddy\WorkBuddy\2026-10-12-08-53-54', true, '{"DisallowStartIfOnBatteries": "false", "StopIfGoingOnBatteries": "false", "ExecutionTimeLimit": "PT30M", "MultipleInstancesPolicy": "IgnoreNew", "StartWhenAvailable": "true", "IdleSettings": {"Duration": "PT10M", "WaitTimeout": "PT1H", "StopOnIdleEnd": "true", "RestartOnIdle": "false"}, "UseUnifiedSchedulingEngine": "true"}'::jsonb, '<?xml version="1.0" encoding="UTF-16"?>

<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">

  <RegistrationInfo>

    <Description>WorkBuddy boot check-in: silent, console-free, no window</Description>

    <URI>\WorkBuddyBootCheckin</URI>

  </RegistrationInfo>

  <Principals>

    <Principal id="Author">

      <UserId>S-1-5-21-2080283827-557422376-331876023-500</UserId>

      <LogonType>InteractiveToken</LogonType>

    </Principal>

  </Principals>

  <Settings>

    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>

    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>

    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>

    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>

    <StartWhenAvailable>true</StartWhenAvailable>

    <IdleSettings>

      <Duration>PT10M</Duration>

      <WaitTimeout>PT1H</WaitTimeout>

      <StopOnIdleEnd>true</StopOnIdleEnd>

      <RestartOnIdle>false</RestartOnIdle>

    </IdleSettings>

    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>

  </Settings>

  <Triggers>

    <LogonTrigger>

      <Delay>PT30S</Delay>

      <UserId>PC-20260923QRMI\Administrator</UserId>

    </LogonTrigger>

  </Triggers>

  <Actions Context="Author">

    <Exec>

      <Command>C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe</Command>

      <Arguments>"C:\Users\Administrator\WorkBuddy\WorkBuddy\2026-10-12-08-53-54\boot_network_checkin.py"</Arguments>

      <WorkingDirectory>C:\Users\Administrator\WorkBuddy\WorkBuddy\2026-10-12-08-53-54</WorkingDirectory>

    </Exec>

  </Actions>

</Task>
' WHERE NOT EXISTS (SELECT 1 FROM archived_scheduled_tasks t WHERE t.package_id = (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27') AND t.task_name = 'WorkBuddyBootCheckin')
UNION ALL
SELECT (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27'), 'WorkBuddyCookieKeepalive', NULL, 'CalendarTrigger', '{"StartBoundary": "2026-10-27T09:15:00", "ScheduleByDay": {"DaysInterval": "1"}}'::jsonb, 'S-1-5-21-2080283827-557422376-331876023-500', 'InteractiveToken', 'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe', 'D:\Workduddy\2026-10-26-10-19-01\workbuddy-cloud-automation\cookie_keepalive.py', NULL, false, '{"DisallowStartIfOnBatteries": "true", "StopIfGoingOnBatteries": "true", "Enabled": "false", "MultipleInstancesPolicy": "IgnoreNew", "IdleSettings": {"Duration": "PT10M", "WaitTimeout": "PT1H", "StopOnIdleEnd": "true", "RestartOnIdle": "false"}}'::jsonb, '<?xml version="1.0" encoding="UTF-16"?>

<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">

  <RegistrationInfo>

    <Date>2026-10-27T13:07:35</Date>

    <Author>PC-20260923QRMI\Administrator</Author>

    <URI>\WorkBuddyCookieKeepalive</URI>

  </RegistrationInfo>

  <Principals>

    <Principal id="Author">

      <UserId>S-1-5-21-2080283827-557422376-331876023-500</UserId>

      <LogonType>InteractiveToken</LogonType>

    </Principal>

  </Principals>

  <Settings>

    <DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>

    <StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>

    <Enabled>false</Enabled>

    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>

    <IdleSettings>

      <Duration>PT10M</Duration>

      <WaitTimeout>PT1H</WaitTimeout>

      <StopOnIdleEnd>true</StopOnIdleEnd>

      <RestartOnIdle>false</RestartOnIdle>

    </IdleSettings>

  </Settings>

  <Triggers>

    <CalendarTrigger>

      <StartBoundary>2026-10-27T09:15:00</StartBoundary>

      <ScheduleByDay>

        <DaysInterval>1</DaysInterval>

      </ScheduleByDay>

    </CalendarTrigger>

  </Triggers>

  <Actions Context="Author">

    <Exec>

      <Command>C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe</Command>

      <Arguments>D:\Workduddy\2026-10-26-10-19-01\workbuddy-cloud-automation\cookie_keepalive.py</Arguments>

    </Exec>

  </Actions>

</Task>
' WHERE NOT EXISTS (SELECT 1 FROM archived_scheduled_tasks t WHERE t.package_id = (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27') AND t.task_name = 'WorkBuddyCookieKeepalive')
UNION ALL
SELECT (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27'), 'WorkBuddyTravelWatch', 'WorkBuddy cat travel monitor: wait for arrival, claim reward, try to depart again', 'LogonTrigger', '{"Delay": "PT1M30S", "UserId": "PC-20260923QRMI\\Administrator"}'::jsonb, 'S-1-5-21-2080283827-557422376-331876023-500', 'InteractiveToken', 'C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe', '"C:\Users\Administrator\WorkBuddy\WorkBuddy\2026-10-12-08-53-54\travel_watch.py" --max-minutes 20', 'C:\Users\Administrator\WorkBuddy\WorkBuddy\2026-10-12-08-53-54', true, '{"DisallowStartIfOnBatteries": "false", "StopIfGoingOnBatteries": "false", "ExecutionTimeLimit": "PT30M", "MultipleInstancesPolicy": "IgnoreNew", "StartWhenAvailable": "true", "IdleSettings": {"Duration": "PT10M", "WaitTimeout": "PT1H", "StopOnIdleEnd": "true", "RestartOnIdle": "false"}, "UseUnifiedSchedulingEngine": "true"}'::jsonb, '<?xml version="1.0" encoding="UTF-16"?>

<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">

  <RegistrationInfo>

    <Description>WorkBuddy cat travel monitor: wait for arrival, claim reward, try to depart again</Description>

    <URI>\WorkBuddyTravelWatch</URI>

  </RegistrationInfo>

  <Principals>

    <Principal id="Author">

      <UserId>S-1-5-21-2080283827-557422376-331876023-500</UserId>

      <LogonType>InteractiveToken</LogonType>

    </Principal>

  </Principals>

  <Settings>

    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>

    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>

    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>

    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>

    <StartWhenAvailable>true</StartWhenAvailable>

    <IdleSettings>

      <Duration>PT10M</Duration>

      <WaitTimeout>PT1H</WaitTimeout>

      <StopOnIdleEnd>true</StopOnIdleEnd>

      <RestartOnIdle>false</RestartOnIdle>

    </IdleSettings>

    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>

  </Settings>

  <Triggers>

    <LogonTrigger>

      <Delay>PT1M30S</Delay>

      <UserId>PC-20260923QRMI\Administrator</UserId>

    </LogonTrigger>

  </Triggers>

  <Actions Context="Author">

    <Exec>

      <Command>C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\pythonw.exe</Command>

      <Arguments>"C:\Users\Administrator\WorkBuddy\WorkBuddy\2026-10-12-08-53-54\travel_watch.py" --max-minutes 20</Arguments>

      <WorkingDirectory>C:\Users\Administrator\WorkBuddy\WorkBuddy\2026-10-12-08-53-54</WorkingDirectory>

    </Exec>

  </Actions>

</Task>
' WHERE NOT EXISTS (SELECT 1 FROM archived_scheduled_tasks t WHERE t.package_id = (SELECT id FROM archived_task_packages WHERE package_name = 'buddy-keeper-archive-2026-10-27') AND t.task_name = 'WorkBuddyTravelWatch');
