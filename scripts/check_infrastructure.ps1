$env:PYTHONPATH = (Join-Path $PSScriptRoot "..\src")
$ErrorActionPreference = "Stop"

$configJson = @'
from campusmind.config import get_settings
import json
s = get_settings()
print(json.dumps({
    "postgres": {"host": s.postgres_host, "port": s.postgres_port},
    "neo4j": {"host": s.neo4j_uri.split("://", 1)[-1].split(":", 1)[0], "port": int(s.neo4j_uri.rsplit(":", 1)[-1])},
    "redis": {"host": s.redis_host, "port": s.redis_port},
    "rustfs": {"host": s.rustfs_endpoint.split("://", 1)[-1].split(":", 1)[0], "port": int(s.rustfs_endpoint.rsplit(":", 1)[-1])}
}))
'@ | python -

$config = $configJson | ConvertFrom-Json
$targets = @(
    @{ Name = "PostgreSQL"; Host = $config.postgres.host; Port = $config.postgres.port },
    @{ Name = "Neo4j"; Host = $config.neo4j.host; Port = $config.neo4j.port },
    @{ Name = "Redis"; Host = $config.redis.host; Port = $config.redis.port },
    @{ Name = "RustFS"; Host = $config.rustfs.host; Port = $config.rustfs.port }
)

foreach ($target in $targets) {
    $result = Test-NetConnection -ComputerName $target.Host -Port $target.Port -WarningAction SilentlyContinue
    [PSCustomObject]@{
        Service = $target.Name
        Endpoint = "$($target.Host):$($target.Port)"
        TcpSucceeded = $result.TcpTestSucceeded
    }
}
