FROM nginx:alpine

COPY ratelimit.conf /etc/nginx/conf.d/00-ratelimit.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY sw.js /usr/share/nginx/html/sw.js
COPY manifest.json /usr/share/nginx/html/manifest.json
COPY favicon.ico /usr/share/nginx/html/favicon.ico
COPY icon-16.png /usr/share/nginx/html/icon-16.png
COPY icon-32.png /usr/share/nginx/html/icon-32.png
COPY icon-180.png /usr/share/nginx/html/icon-180.png
COPY icon-192.png /usr/share/nginx/html/icon-192.png
COPY icon-512.png /usr/share/nginx/html/icon-512.png

EXPOSE 80
