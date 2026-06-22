FROM wordpress:6-apache

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Honeypot log helper — watches wp-fail2ban-style logs
RUN mkdir -p /var/log/honeypot && chmod 777 /var/log/honeypot

# Expose wp-config.php with fake credentials
RUN { \
    echo '<?php'; \
    echo "define('DB_NAME', 'wordpress');"; \
    echo "define('DB_USER', 'wp_admin');"; \
    echo "define('DB_PASSWORD', 'Welcome2024!');"; \
    echo "define('DB_HOST', 'localhost');"; \
    echo "define('DB_CHARSET', 'utf8');"; \
    echo "define('DB_COLLATE', '');"; \
    echo "define('AUTH_KEY',         '$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 40 | head -1)');"; \
    echo "define('SECURE_AUTH_KEY',  '$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 40 | head -1)');"; \
    echo "define('LOGGED_IN_KEY',    '$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 40 | head -1)');"; \
    echo "define('NONCE_KEY',        '$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 40 | head -1)');"; \
    echo "define('AUTH_SALT',        '$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 40 | head -1)');"; \
    echo "define('SECURE_AUTH_SALT', '$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 40 | head -1)');"; \
    echo "define('LOGGED_IN_SALT',   '$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 40 | head -1)');"; \
    echo "define('NONCE_SALT',       '$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 40 | head -1)');"; \
    echo "define('WP_DEBUG', true);"; \
    echo "define('WP_DEBUG_LOG', '/var/log/honeypot/wp-debug.log');"; \
    echo "define('WP_DEBUG_DISPLAY', false);"; \
    echo "define('WP_POST_REVISIONS', 5);"; \
    echo "/** Enable XML-RPC for remote publishing (vulnerable) */"; \
    echo "define('XMLRPC_ENABLED', true);"; \
    echo "/** Disable file editing from admin (but keep uploads open) */"; \
    echo "define('DISALLOW_FILE_EDIT', false);"; \
    echo ''; \
    echo "if (!defined('ABSPATH')) define('ABSPATH', __DIR__ . '/');"; \
    echo "require_once ABSPATH . 'wp-settings.php';"; \
    } > /var/www/html/wp-config.php

# Log watcher that writes honeypot-style JSON events to shared volume
COPY log_watcher.py /usr/local/bin/log_watcher.py
RUN chmod +x /usr/local/bin/log_watcher.py

# Cron: every 30s watch Apache access log for login attempts
RUN echo "* * * * * root python3 /usr/local/bin/log_watcher.py >> /var/log/honeypot/wordpress.json 2>&1" > /etc/cron.d/honeypot
RUN chmod 0644 /etc/cron.d/honeypot

# Install vulnerable plugins (simulated)
RUN mkdir -p /var/www/html/wp-content/plugins/vulnerable-plugin && \
    echo "<?php /* Vulnerable plugin v1.0 — for training purposes */" > /var/www/html/wp-content/plugins/vulnerable-plugin/index.php
