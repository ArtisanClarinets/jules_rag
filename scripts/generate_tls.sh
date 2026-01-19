#!/bin/bash
mkdir -p infra/nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout infra/nginx/certs/server.key \
  -out infra/nginx/certs/server.crt \
  -subj "/C=US/ST=State/L=City/O=Vantus/CN=localhost"
echo "Generated self-signed certs in infra/nginx/certs"
