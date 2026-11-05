$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\..
$pg = 'C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe'
& $pg -D .runtime\pgdata status *> $null
if ($LASTEXITCODE -ne 0) { & $pg -D .runtime\pgdata -l .runtime\postgres.log -o '-p 55432 -h 127.0.0.1' start }
$redis = Get-ChildItem .runtime\redis-modern -Recurse -Filter redis-server.exe | Select-Object -First 1
$tcp = New-Object System.Net.Sockets.TcpClient
try { $tcp.Connect('127.0.0.1', 6380) } catch {
    Start-Process -FilePath $redis.FullName -ArgumentList '--bind 127.0.0.1 --port 6380 --appendonly yes --dir .runtime/redis-modern' -WindowStyle Hidden
} finally { $tcp.Dispose() }
& .\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
& .\.venv\Scripts\python.exe -m app
