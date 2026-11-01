# Inicia una instancia MongoDB local como replica set de un solo nodo (rs0)
# en el puerto 27018, con datos en .mongodb-data/ del propio proyecto.
#
# ¿Por qué? Mongo standalone no soporta transacciones multi-documento, y el
# dominio las necesita para reservas de inventario y pruebas de concurrencia.
# El servicio MongoDB instalado en 27017 queda intacto y no se usa.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$bin = 'C:\Program Files\MongoDB\Server\9.0\bin\mongod.exe'
$dataDir = Join-Path $root '.mongodb-data'
$devPort = 27018

# --- 1. Comprobar específicamente la instancia de desarrollo (puerto 27018) ---

function Test-PortListening([int]$Port) {
    $conn = New-Object Net.Sockets.TcpClient
    try {
        $conn.Connect('127.0.0.1', $Port)
        return $true
    } catch {
        return $false
    } finally {
        $conn.Close()
    }
}

function Test-DevMongoRunning {
    # Criterio 1: el puerto 27018 responde.
    if (Test-PortListening -Port $devPort) {
        # Verificar que quien escucha realmente es un mongod de este proyecto,
        # descartando otro proceso ajeno que ocupe el puerto.
        $mongodOnPort = Get-CimInstance Win32_Process -Filter "Name='mongod.exe'" |
            Where-Object { $_.CommandLine -match "--port $devPort|27018" }
        if ($mongodOnPort) {
            Write-Host "Instancia de desarrollo ya activa en el puerto $devPort. No se hace nada."
            return $true
        }
        Write-Warning "El puerto $devPort está ocupado por un proceso que NO es mongod:"
        $owner = Get-NetTCPConnection -LocalPort $devPort -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($owner) {
            Get-Process -Id $owner.OwningProcess |
                Select-Object Id, ProcessName | Format-Table
        }
        throw "Libera el puerto $devPort o revisa la configuración de desarrollo."
    }
    # Criterio 2: aunque existan otros mongod (p. ej. el servicio del 27017),
    # la instancia de desarrollo no está levantada.
    $otherMongod = Get-Process mongod -ErrorAction SilentlyContinue
    if ($otherMongod) {
        Write-Host "Detectado mongod ajeno a esta instancia (servicio 27017 u otro). No afecta: la instancia de desarrollo usará el puerto $devPort."
    }
    return $false
}

if (Test-DevMongoRunning) {
    exit 0
}

# --- 2. Levantar la instancia de desarrollo ---

New-Item -ItemType Directory -Force $dataDir | Out-Null

Start-Process -FilePath $bin -ArgumentList @(
    '--replSet', 'rs0',
    '--port', "$devPort",
    '--dbpath', $dataDir,
    '--bind_ip', '127.0.0.1',
    '--logpath', (Join-Path $dataDir 'mongod.log')
)

# --- 3. Esperar a que el puerto responda (hasta 20 s) ---

$deadline = (Get-Date).AddSeconds(20)
while (-not (Test-PortListening -Port $devPort)) {
    if ((Get-Date) -gt $deadline) {
        $log = Join-Path $dataDir 'mongod.log'
        if (Test-Path $log) {
            Write-Warning 'mongod no respondió a tiempo. Últimas líneas del log:'
            Get-Content $log -Tail 20
        }
        throw "mongod no quedó a la escucha en el puerto $devPort."
    }
    Start-Sleep -Milliseconds 500
}

Write-Host "mongod (rs0) a la escucha en el puerto $devPort."

# --- 4. Iniciar el replica set si falta (idempotente) ---

uv run python "$PSScriptRoot\init_replica_set.py"
