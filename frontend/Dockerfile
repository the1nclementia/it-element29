FROM nginx:1.30.6-alpine
COPY frontend/index.html /usr/share/nginx/html/index.html
COPY frontend/status.js /usr/share/nginx/html/status.js
COPY frontend/status.css /usr/share/nginx/html/status.css
COPY assets/brand /usr/share/nginx/html/brand
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
