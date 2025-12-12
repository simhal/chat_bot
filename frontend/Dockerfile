# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Build arguments for environment variables
ARG PUBLIC_API_URL
ARG PUBLIC_LINKEDIN_CLIENT_ID
ARG PUBLIC_LINKEDIN_REDIRECT_URI

# Set as environment variables for the build
ENV PUBLIC_API_URL=$PUBLIC_API_URL
ENV PUBLIC_LINKEDIN_CLIENT_ID=$PUBLIC_LINKEDIN_CLIENT_ID
ENV PUBLIC_LINKEDIN_REDIRECT_URI=$PUBLIC_LINKEDIN_REDIRECT_URI

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application (env vars will be embedded)
RUN npm run build

# Production stage
FROM node:20-alpine

WORKDIR /app

# Copy built application
COPY --from=builder /app/build ./build
COPY --from=builder /app/package*.json ./

# Install only production dependencies
RUN npm install --omit=dev

# Expose port
EXPOSE 3000

# Set environment variable for production
ENV NODE_ENV=production

# Run the application
CMD ["node", "build"]
