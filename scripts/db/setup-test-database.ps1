<#
.SYNOPSIS
    Creates and migrates the isolated PostgreSQL database used by the backend
    integration tests (default: touche_commerce_test).

.DESCRIPTION
    Reads the connection settings from .env, connects as the bootstrap
    superuser, creates the database owned by the migration role, applies the
    shared schema grants and runs Alembic to head.

    The integration suite refuses to run against anything except this database
    (it is derived from the configured DSNs by swapping the database name), so a
    development or production database can never be truncated by a test run.

.PARAMETER Force
    Drop and recreate the database. Destroys only test data.

.PARAMETER SkipMigration
    Create the database but do not run Alembic (the test fixture also upgrades).
#>
param(
    [switch] $Force,
    [switch] $SkipMigration
)

. "$PSScriptRoot\..\lib\common.ps1"

$repoRoot = Get-RepoRoot
$backendDir = Join-Path $repoRoot 'backend'
$testDatabase = if ($env:TOUCHE_TEST_DATABASE_NAME) { $env:TOUCHE_TEST_DATABASE_NAME } else { 'touche_commerce_test' }

Import-DotEnv

$adminUser = Get-RequiredEnv 'POSTGRES_ADMIN_USER'
$adminPassword = Get-RequiredEnv 'POSTGRES_ADMIN_PASSWORD'
$host_ = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { '127.0.0.1' }
$port = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { '5432' }
$migratorUser = Get-RequiredEnv 'TOUCHE_DB_MIGRATOR_USER'
$appUser = Get-RequiredEnv 'TOUCHE_DB_APP_USER'
$psql = Join-Path (Get-PostgresBin) 'psql.exe'

$previousPassword = $env:PGPASSWORD
$env:PGPASSWORD = $adminPassword
try {
    Write-Step "Ensuring database $testDatabase exists"
    $exists = (& $psql -h $host_ -p $port -U $adminUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$testDatabase'").Trim()
    if ($Force -and $exists -eq '1') {
        & $psql -h $host_ -p $port -U $adminUser -d postgres -v ON_ERROR_STOP=1 -q -c "DROP DATABASE IF EXISTS `"$testDatabase`" WITH (FORCE)"
        if ($LASTEXITCODE -ne 0) { throw 'Failed to drop the test database.' }
        $exists = ''
    }
    if ($exists -ne '1') {
        & $psql -h $host_ -p $port -U $adminUser -d postgres -v ON_ERROR_STOP=1 -q -c "CREATE DATABASE `"$testDatabase`" OWNER `"$migratorUser`""
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create the test database.' }
        Write-Ok "created $testDatabase"
    }
    else {
        Write-Ok "$testDatabase already exists"
    }

    & $psql -h $host_ -p $port -U $adminUser -d $testDatabase -v ON_ERROR_STOP=1 -q `
        -v app_user=$appUser -v migrator_user=$migratorUser `
        -f (Join-Path $repoRoot 'scripts\db\02-schema-grants.sql')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to apply schema grants to the test database.' }
    Write-Ok 'schema grants applied'
}
finally {
    $env:PGPASSWORD = $previousPassword
}

if (-not $SkipMigration) {
    $migrationUrl = Get-RequiredEnv 'TOUCHE_DATABASE_MIGRATION_URL'
    $separator = $migrationUrl.LastIndexOf('/')
    if ($separator -lt 0) { throw 'TOUCHE_DATABASE_MIGRATION_URL does not contain a database name.' }
    $testMigrationUrl = $migrationUrl.Substring(0, $separator + 1) + $testDatabase

    Write-Step 'Applying Alembic migrations to the test database'
    $python = Get-BackendPython
    $previousMigrationUrl = $env:TOUCHE_DATABASE_MIGRATION_URL
    $previousEnvironment = $env:TOUCHE_ENVIRONMENT
    try {
        $env:TOUCHE_DATABASE_MIGRATION_URL = $testMigrationUrl
        $env:TOUCHE_ENVIRONMENT = 'test'
        Invoke-Native -FilePath $python -Arguments @('-m', 'alembic', 'upgrade', 'head') -WorkingDirectory $backendDir
        Write-Ok 'test database at head'
    }
    finally {
        $env:TOUCHE_DATABASE_MIGRATION_URL = $previousMigrationUrl
        $env:TOUCHE_ENVIRONMENT = $previousEnvironment
    }
}

Write-Host ''
Write-Host "Test database ready: $testDatabase" -ForegroundColor Green
