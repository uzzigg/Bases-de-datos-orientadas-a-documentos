param(
    [ValidateSet('Validate','Pull','Up','Stop','Status','Logs')][string]$Action = 'Status',
    [ValidateSet('mongo','postgres')][string]$Engine = 'mongo',
    [ValidateSet('A','B','C')][string]$Profile = 'A'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) { & "$PSScriptRoot/iniciar_entorno.ps1" }
    $baseArgs = @('compose','--env-file','.env','--env-file',"config/recursos/$Profile.env",'--profile',$Engine)
    switch ($Action) {
        Validate { & docker @baseArgs config --quiet }
        Pull { & docker @baseArgs pull }
        Up {
            $other = if ($Engine -eq 'mongo') { 'postgresql' } else { 'mongodb' }
            # Un solo motor: detener el opuesto si existe dentro de este proyecto.
            & docker compose --env-file .env --env-file "config/recursos/$Profile.env" --profile '*' stop $other
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo detener el motor opuesto' }
            & docker @baseArgs up -d --wait --wait-timeout 180
            if ($LASTEXITCODE -ne 0) { throw "Docker fallo en Up ($LASTEXITCODE)" }
            $taskPython = Join-Path $projectRoot 'Otros/venv/Scripts/python.exe'
            if (Test-Path -LiteralPath $taskPython) {
                & $taskPython -B "$PSScriptRoot/verificar_preparacion.py" --engine $Engine
                if ($LASTEXITCODE -ne 0) { throw 'La preparación preventiva requiere revisión' }
            }
        }
        Stop { & docker compose --env-file .env --env-file "config/recursos/$Profile.env" --profile '*' stop }
        Status { & docker @baseArgs ps -a }
        Logs { & docker @baseArgs logs --tail 80 }
    }
    if ($LASTEXITCODE -ne 0) { throw "Docker fallo en $Action ($LASTEXITCODE)" }
} finally { Pop-Location }
