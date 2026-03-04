FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY marked.min.js /usr/share/nginx/html/marked.min.js

EXPOSE 80
