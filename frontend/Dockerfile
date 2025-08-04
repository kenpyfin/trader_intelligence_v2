# --- Build Stage ---
# Use a Node.js image to build the React application.
FROM node:18-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm install --prefix frontend react-plotly.js plotly.js
RUN CI=false npm run build


# --- Production Stage ---
# Use a lightweight Nginx image to serve the static files.
FROM nginx:1.25-alpine

# Copy the built application from the 'build' stage to the Nginx public directory.
COPY --from=build /app/build /usr/share/nginx/html

# Copy our custom Nginx configuration template.
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Install gettext for envsubst
RUN apk add --no-cache gettext

# When the container starts, substitute environment variables in the template
# and output the final config to the correct location. Then start Nginx.
CMD ["/bin/sh", "-c", "envsubst '$FRONTEND_PORT $BACKEND_PORT' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
