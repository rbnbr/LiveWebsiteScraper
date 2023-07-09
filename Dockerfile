# install python environment
FROM python:3.11-alpine

# create virtualenv in dir variable
ENV VIRTUAL_ENV=/pyvenv

# create virtual environment and activate it
RUN python -m venv $VIRTUAL_ENV

# add to path to use new python bin from virtualenv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# install libs fro psycopg2 package build
RUN apk add --no-cache postgresql-libs && \
 apk add --no-cache --virtual .build-deps gcc musl-dev postgresql-dev

# install required packages
RUN pip install lxml selenium websockets psycopg2
RUN pip install python-dateutil

# copy application files

# create certs dir to mount certificates
RUN mkdir "certs"

# creates dir (if not exists (it shouldn't!)) and sets it as workdir
WORKDIR "/pyapp"

RUN mkdir "logs"

# add required files
COPY main.py .

COPY src/ src/

# add firefox profiles
COPY firefox_profiles firefox_profiles

# specify firefox profile (path on the remote machine!, the profile has to exist on the remote machine of the selenium)
ENV PYAPP_FIREFOX_PROFILE_DIR firefox_profiles/ff-profile.WithCACertificate

# add default configs
COPY *_config.json .

# specify environment variables
ENV POSTGRESQL_CREDENTIALS_PATH "/run/secrets/postgres_credentials"
#
ENV POSTGRESQL_SCHEMA "public"

# monitor configuration
# the amount of drivers the monitor tries to create and connect. must less or equal the ammount of provided addresses
ENV MAX_BROWSER_INSTANCES 5

# driver adresses (from 1 to MAX_BROWSER_INSTANCES)
ENV SEL_DRIVER_ADDR_1 "http://localhost:5901"
ENV SEL_DRIVER_ADDR_2 "http://localhost:5902"
ENV SEL_DRIVER_ADDR_3 "http://localhost:5903"
ENV SEL_DRIVER_ADDR_4 "http://localhost:5904"
ENV SEL_DRIVER_ADDR_5 "http://localhost:5905"

# after detecting unhealthy page, triggers refresh; if this amount of unhealthy/refresh
# in last MAX_PAGE_UNHEALTHY_COUNT_AGE_S, then raises exception
ENV MAX_PAGE_UNHEALTHY_REFRESH_IN_TIME_LIMIT 5

# the max time in which unhealthy states are being tracked
# should be enough time to trigger the unhealthy option
ENV MAX_PAGE_UNHEALTHY_COUNT_AGE_S 3600

# websocket host url (without port) for the selenium driver to connect to
ENV WS_SERVER_ADDR "live-data-scraper"

# the websocket port to be used
ENV WS_PORT 8001

# whether the websocket should use ssl, cert and key files must be provided at WS_CERT_PATH and WS_KEY_PATH
ENV WS_USE_SSL "True"
ENV WS_CERT_PATH "/certs/cert.crt"
ENV WS_KEY_PATH "/run/secrets/cert.key"

# py app json config path
ENV PYAPP_JSON_CONFIG_PATH "./configs/config.json"

# if True, uses ./default_debug_config.json for unspecified fields in provided config
# if False, uses ./default_config.json as config for unspecified fields in provided config
ENV PYAPP_DEBUG "False"

ENTRYPOINT ["python", "./main.py"]
# ENTRYPOINT ["tail", "-F", "anything"]
