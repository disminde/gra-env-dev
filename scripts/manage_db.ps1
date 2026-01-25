<#
.SYNOPSIS
    简单的数据库管理脚本
.DESCRIPTION
    用于快速启动、停止和重启 PostgreSQL 容器
.EXAMPLE
    .\scripts\manage_db.ps1 -Action start
    .\scripts\manage_db.ps1 -Action stop
#>

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("start", "stop", "restart", "status", "logs")]
    [string]$Action
)

$ComposeFile = "docker-compose.yml"

switch ($Action) {
    "start" {
        Write-Host "🚀 Starting database container..." -ForegroundColor Green
        docker-compose -f $ComposeFile up -d
        Write-Host "✅ Database started." -ForegroundColor Green
    }
    "stop" {
        Write-Host "🛑 Stopping database container..." -ForegroundColor Yellow
        docker-compose -f $ComposeFile down
        Write-Host "✅ Database stopped." -ForegroundColor Green
    }
    "restart" {
        Write-Host "🔄 Restarting database container..." -ForegroundColor Cyan
        docker-compose -f $ComposeFile restart
        Write-Host "✅ Database restarted." -ForegroundColor Green
    }
    "status" {
        docker-compose -f $ComposeFile ps
    }
    "logs" {
        docker-compose -f $ComposeFile logs -f
    }
}
