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
New-Item -ItemType Directory -Force $dataDir | Out-Null

$running = Get-Process mongod -ErrorAction SilentlyContinue
if ($running) {
    Write-Host 'mongod ya está en ejecución:'
    $running | Select-Object Id, ProcessName | Format-Table
    exit 0
}

Start-Process -FilePath $bin -ArgumentList @(
    '--replSet', 'rs0',
    '--port', '27018',
    '--dbpath', $dataDir,
    '--bind_ip', '127.0.0.1',
    '--logpath', (Join-Path $dataDir 'mongod.log')
)

# Espera a que el puerto responda
$deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline) {
    try {
        $tcp = New-Object Net.Sockets.TcpClient
        $tcp.Connect('127.0.0.1', 27018)
        $tcp.Close()
        break
    } catch { Start-Sleep -Milliseconds 500 }
}

uv run python "$PSScriptRoot\init_replica_set.py"
