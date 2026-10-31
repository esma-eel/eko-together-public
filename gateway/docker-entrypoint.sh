#!/bin/sh
set -e

# Default to 'eko-gateway' if GATEWAY_ORIGIN_SECRET is unset or empty
export GATEWAY_ORIGIN_SECRET="${GATEWAY_ORIGIN_SECRET:-eko-gateway}"

# Generate /etc/nginx/nginx.conf from template if the template exists
if [ -f /etc/nginx/templates/nginx.conf.template ]; then
    echo "[api_gateway] Generating /etc/nginx/nginx.conf from template (substituting GATEWAY_ORIGIN_SECRET)..."
    # IMPORTANT: Only substitute ${GATEWAY_ORIGIN_SECRET} so Nginx runtime variables ($host, $remote_addr, $msec, etc.) remain intact
    envsubst '${GATEWAY_ORIGIN_SECRET}' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/nginx.conf
fi

exec "$@"

