#!/bin/sh
# Substitute only API_UPSTREAM in the nginx template, preserving all
# nginx $variables (like $uri, $proxy_host, etc.) untouched.
envsubst '${API_UPSTREAM}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
