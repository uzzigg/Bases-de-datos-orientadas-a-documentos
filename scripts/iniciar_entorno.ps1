$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envPath) {
    Write-Host '.env ya existe; se conserva.'
    return
}
function New-LocalPassword {
    $bytes = [byte[]]::new(32)
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
$template = Get-Content -Raw -LiteralPath (Join-Path $projectRoot '.env.example')
$template = $template.Replace('GENERATE_MONGO', (New-LocalPassword)).Replace('GENERATE_POSTGRES', (New-LocalPassword))
[IO.File]::WriteAllText($envPath, $template, [Text.UTF8Encoding]::new($false))
Write-Host '.env creado con credenciales aleatorias locales; no se imprimen.'
