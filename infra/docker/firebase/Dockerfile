FROM node:22-bookworm-slim
RUN npm install -g firebase-tools@13.29.1
WORKDIR /srv
COPY firebase.json .firebaserc ./
EXPOSE 9099
CMD ["firebase", "emulators:start", "--only", "auth", "--project", "demo-younique"]
