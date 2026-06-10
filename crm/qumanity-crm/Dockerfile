FROM node:20-bookworm-slim

WORKDIR /app

# .npmrc enables legacy-peer-deps for all npm commands in this image
COPY package.json .npmrc .env.example ./
COPY plugins ./plugins
COPY client ./client

RUN npm install --legacy-peer-deps

ENV NODE_ENV=production
EXPOSE 3000

CMD ["sh", "-c", "npx nocobase install --skip-install-deps && npx nocobase start"]
