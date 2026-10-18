# Serve static Docusaurus build
FROM node:24-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=builder /app/build /usr/share/nginx/html
# Docusaurus is mounted under /docs
RUN printf '%s\n' \
  'server {' \
  '  listen 80;' \
  '  server_name _;' \
  '  location /docs/ {' \
  '    alias /usr/share/nginx/html/;' \
  '    try_files $uri $uri/ /docs/index.html;' \
  '  }' \
  '  location = /docs {' \
  '    return 301 /docs/;' \
  '  }' \
  '  root /usr/share/nginx/html;' \
  '}' > /etc/nginx/conf.d/default.conf
EXPOSE 80
