FROM nginxinc/nginx-unprivileged:1.31.3-alpine

LABEL org.opencontainers.image.title="CS336 Lectures"
LABEL org.opencontainers.image.description="Static CS336 lecture viewer, traces, and PDFs"
LABEL org.opencontainers.image.source="https://github.com/sky-bro/cs336-lectures"

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chown=101:101 index.html viewer.html /usr/share/nginx/html/
COPY --chown=101:101 assets/ /usr/share/nginx/html/assets/
COPY --chown=101:101 images/ /usr/share/nginx/html/images/
COPY --chown=101:101 var/ /usr/share/nginx/html/var/
COPY --chown=101:101 lecture_*.pdf /usr/share/nginx/html/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
