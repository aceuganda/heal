#!/bin/bash

# Define paths
data_path="../data/certbot"
domain=$(grep DOMAIN .env.nginx | cut -d= -f2)

echo "### Stopping the current containers..."
docker compose -f docker-compose.prod.yml -p danswer-stack down

echo "### Removing Let's Encrypt certificate files..."
rm -rf "$data_path/conf/live/$domain"
rm -rf "$data_path/conf/archive/$domain"
rm -rf "$data_path/conf/renewal/$domain.conf"

# Remove the options-ssl-nginx.conf and ssl-dhparams.pem files
echo "### Removing TLS parameter files..."
rm -f "$data_path/conf/options-ssl-nginx.conf"
rm -f "$data_path/conf/ssl-dhparams.pem"

echo "### Restoring original Nginx configuration..."
# If you have a backup of your original Nginx configuration, restore it
# Otherwise, modify your app.conf.template.dev to remove SSL-related directives

echo "### Cleaning up..."
# Remove any remaining SSL-related directories
rm -rf "$data_path/www/.well-known"

echo "### Changes from the SSL setup script have been undone."
echo "### You'll need to restart your containers with the updated configuration."
echo "### Run: docker compose -f docker-compose.prod.yml -p danswer-stack up -d"