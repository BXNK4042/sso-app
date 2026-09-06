FROM alpine:latest

# Add freeradius-ldap alongside the core packages
RUN apk update && apk add --no-cache \
    freeradius \
    freeradius-ldap \
    freeradius-utils

# Copy your configuration files
COPY config/radiusd.conf /etc/raddb/radiusd.conf
COPY config/clients.conf /etc/raddb/clients.conf
COPY config/users /etc/raddb/users

EXPOSE 1812/udp 1813/udp

CMD ["radiusd", "-X"]