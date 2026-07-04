# OpenBao server configuration — RevOS production.
#
# Storage: local filesystem (single Hetzner node).
# TLS: disabled here; Caddy terminates TLS at the edge.
#      The OpenBao port (8200) is bound to localhost only in docker-compose,
#      so it is never reachable from outside the Docker network.
#
# After first deploy, run:  deploy/bao-setup.sh

storage "file" {
  path = "/vault/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

api_addr = "http://openbao:8200"
ui       = false
