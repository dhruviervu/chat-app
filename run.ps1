param(
  [switch]$Detach
)

if ($Detach) {
  docker compose up --build -d
} else {
  docker compose up --build
}

