ARG PLAYWRIGHT_IMAGE
FROM ${PLAYWRIGHT_IMAGE}
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --ignore-scripts && npm cache clean --force
COPY server.js ./
USER pwuser
EXPOSE 3010
CMD ["node", "server.js"]
