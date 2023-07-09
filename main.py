import json
import os
import pathlib
from datetime import datetime
import time

import psycopg2

import logging
from src.logger import make_logger
from src.util import get_env_non_empty
from src.abc.monitor_manager import MonitorManager

import ssl

filename = "logs/{}.log".format(datetime.fromtimestamp(time.time()).strftime("%d-%m-%Y_%H-%M-%S"))

logger = make_logger(name="scraper_logger", filename=filename, stream=True)

logging.basicConfig(encoding="utf-8")  # cannot use this prior to Python3.9


def get_websocket_port_and_context_from_env():
    port = int(get_env_non_empty("WS_PORT", default=8001))
    logger.info(f"The pyapp websocket will use port: {port}")

    cert_path = pathlib.Path(get_env_non_empty("WS_CERT_PATH", default="/certs/cert.crt"))
    key_path = pathlib.Path(get_env_non_empty("WS_KEY_PATH", default="/run/secrets/cert.key"))

    use_ssl = get_env_non_empty("WS_USE_SSL", default="False").lower() == "true"
    if not use_ssl:
        logger.info("The pyapp websocket will not use ssl as specified by envvar WS_USE_SSL")
        ssl_context = None
    else:
        if cert_path.exists() and key_path.exists():
            logger.info(f"found cert path ({cert_path}) and key path ({key_path}), will use ssl for websocket")
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        else:
            logger.critical(f"did not find cert path ({cert_path}) or key path ({key_path}) even though "
                            f"WS_USE_SSL was set to true... exit the application")
            raise RuntimeError("failed to find certificate and key for websocket")

    return port, ssl_context


def get_postgresql_connection():
    filepath = pathlib.Path(get_env_non_empty("POSTGRESQL_CREDENTIALS_PATH",
                                              default="/run/secrets/postgres_credentials"))

    with open(filepath, "rt") as f:
        credentials = f.read()

    conn = psycopg2.connect(credentials)

    return conn


def main():
    PYAPP_JSON_CONFIG_PATH = get_env_non_empty("PYAPP_JSON_CONFIG_PATH", default="./config.json")

    PYAPP_DEBUG = os.getenv("PYAPP_DEBUG", default="False")
    debug = PYAPP_DEBUG.lower() == "true"

    if not debug:
        logger.info("running in regular mode")

        with open("./default_config.json", "rt") as f:
            default_config = json.load(f)
    else:
        # debug mode
        logger.info("running in debug mode")

        with open("./default_debug_config.json", "rt") as f:
            default_config = json.load(f)

    try:
        with open(PYAPP_JSON_CONFIG_PATH, "rt") as f:
            config = json.load(f)
        logger.info("found specific config file... use it to override default config")

        # override default_config with fields of config
        default_config.update(config)
    except FileNotFoundError:
        logger.info(f"did not find config file '{PYAPP_JSON_CONFIG_PATH}', using default config")

    config = default_config

    logger.info(f"using config parameters: {json.dumps(config)}")

    push_interval_s = config["push_interval_s"]
    update_tabs_interval_s = config["update_tabs_interval_s"]
    browser_instances_n = config["browser_instances_n"]
    headless = config["headless"]
    headless_first_override = config["headless_first_override"]
    health_check_interval_s = config["health_check_interval_s"]
    simulate_activity_interval_s = config["simulate_activity_interval_s"]

    ws_port, ws_ssl_context = get_websocket_port_and_context_from_env()

    postgres_connection = None  # get_postgresql_connection()
    schema = get_env_non_empty("POSTGRESQL_SCHEMA", "public")

    monitor_manager = MonitorManager(
        push_interval_s=push_interval_s,
        update_tabs_interval_s=update_tabs_interval_s,
        browser_instances_n=browser_instances_n,
        headless=headless,
        headless_first_override=headless_first_override,
        health_check_interval_s=health_check_interval_s,
        ws_port=ws_port,
        ws_ssl_context=ws_ssl_context,
        simulate_activity_interval_s=simulate_activity_interval_s,
        postgres_connection=postgres_connection,
        schema=schema,
    )

    monitor_manager.run()


if __name__ == '__main__':
    main()
