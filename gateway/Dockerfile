FROM nginx:1.27-alpine

# Remove default configuration
RUN rm -f /etc/nginx/conf.d/default.conf

# Environment defaults
ENV GATEWAY_ORIGIN_SECRET=eko-gateway

# Copy template, entrypoint script, and static UI assets
COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
COPY static/ /usr/share/nginx/html/

# Pre-generate /etc/nginx/nginx.conf with defaults during build
RUN envsubst '${GATEWAY_ORIGIN_SECRET}' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/nginx.conf

# Healthcheck to probe gateway availability
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost/health | grep -q "healthy" || exit 1

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
