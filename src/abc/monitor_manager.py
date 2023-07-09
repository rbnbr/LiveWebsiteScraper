import asyncio
import json
import pathlib
import time
import warnings
import concurrent.futures
import logging

import urllib3.exceptions

from src.abc.driver_monitor import DriverManager
from src.page_monitors.random_signal_spm import RandomSignalSPM
from src.abc.single_page_monitoring import SinglePageMonitoring
from src.util import make_do_in_interval_fn, \
    append_element_dict_to_list_dict, get_env_non_empty

from selenium.webdriver import FirefoxOptions
import websockets
import threading

logger = logging.getLogger("scraper_logger")


SPM_Classes = [
    RandomSignalSPM
]


class MonitorManager:
    """
    A class to monitor the https://rbnbr.github.io/random-signal website.

    NOTE: This class could hold multiple Driver Managers and each could hold multiple page managers, depending on
        the use case. It could be used to monitor dozens of possibly different pages.
    """

    MAX_BROWSER_INSTANCES = int(get_env_non_empty("MAX_BROWSER_INSTANCES", default=5))

    _LOCAL_DRIVER_ADDR_FMT = "http://{}:{}"

    # after detecting unhealthy page, triggers refresh; if this amount of unhealthy/refresh
    # in last MAX_PAGE_UNHEALTHY_COUNT_AGE_S, then raises exception
    MAX_PAGE_UNHEALTHY_REFRESH_IN_TIME_LIMIT = int(
        get_env_non_empty("MAX_PAGE_UNHEALTHY_REFRESH_IN_TIME_LIMIT", 5))

    # the max time in which unhealthy states are being tracked
    # should be enough time to trigger the unhealthy option
    MAX_PAGE_UNHEALTHY_COUNT_AGE_S = int(get_env_non_empty("MAX_PAGE_UNHEALTHY_COUNT_AGE_S", default=3600))

    def __init__(self, push_interval_s: float = 60, update_tabs_interval_s: float = 60 * 15,
                 browser_instances_n: int = 1, health_check_interval_s: float = 30,
                 *, ws_port=8001, ws_ssl_context=None, simulate_activity_interval_s=60,
                 headless: bool = True, headless_first_override: bool = None,
                 postgres_connection=None, schema: str = "public"):
        """
        :param push_interval_s: Interval of retrieving data from individual page managers and pushing it to the database
        :param update_tabs_interval_s: Interval to check whether tabs are still all being monitored. The update_tabs(..)
            method can integrate logic to also open or close tabs etc.
        :param browser_instances_n: Amount of browser instances (remote selenium drivers) we can leverage.
            Depends on the traffic and compute capabilities. Regular use-cases do not need more than one.
        :param health_check_interval_s: interval to check the health of individual page managers
        :param ws_port: port of the websocket server
        :param ws_ssl_context: secure websocket context (includes certificates etc.)
        :param simulate_activity_interval_s: interval of calling 'simulate activity' for each individual page manager
        :param headless: if remote driver should run headless
        :param headless_first_override: if using multiple browser/driver instances, this can be used start all in
            headless except the first one. Used for debugging purposes.
        :param postgres_connection: Postgres' connection used to push data into the database. (Assuming we use postgres)
        :param schema: Postgres schema to be used.
        """
        if browser_instances_n > self.MAX_BROWSER_INSTANCES:
            warnings.warn(f"maximum amount of browsers is limited to {self.MAX_BROWSER_INSTANCES}, "
                          f"got {browser_instances_n}; override it with {self.MAX_BROWSER_INSTANCES}")
            browser_instances_n = self.MAX_BROWSER_INSTANCES

        self.push_interval_s = push_interval_s
        self.update_tabs_interval_s = update_tabs_interval_s
        self.browser_instances_n = browser_instances_n
        self.headless = headless
        self.headless_first_override = headless_first_override
        self.health_check_interval_s = health_check_interval_s
        self.postgres_connection = postgres_connection
        self.schema = schema

        self.driver_managers: dict[int, DriverManager] \
            = self.make_remote_driver_managers(self.browser_instances_n, self.headless, self.headless_first_override,
                                               max_time_for_retries_s=60)

        self.health_stati = dict()

        self.ws_port = ws_port
        self._ws_ssl_context = ws_ssl_context
        self._websocket_thread = None
        self._should_stop = False

        self._should_destroy = False

        self.simulate_activity_interval_s = simulate_activity_interval_s

    def get_addresses(self):
        """
        Get addresses of remote selenium nodes from env.
        :return:
        """
        return [
            get_env_non_empty(f"SEL_DRIVER_ADDR_{i}",
                              default=self._LOCAL_DRIVER_ADDR_FMT.format("localhost", 5900 + i)) for i in
            range(1, self.MAX_BROWSER_INSTANCES + 1)
        ]

    async def ws_page_distributor_handler(self, websocket):
        async for message in websocket:
            data_json = json.loads(message)

            # get page_url to distribute to single page manager
            page_url = data_json["page_url"]

            driver_manager = None

            # find drm for page url
            for drm in self.driver_managers:
                if self.driver_managers[drm].is_monitoring_url(page_url):
                    driver_manager = self.driver_managers[drm]
                    break

            if driver_manager is None:
                logger.warning(f"got connection from page url which is not being monitored {page_url}... "
                               f"close connection")
                return

            # find page manager
            page_manager = driver_manager.page_managers[page_url]

            # add data to page manager
            page_manager.add_page_data(data_json)

    async def _async_while_not_stopped(self):
        while not self._should_stop:
            await asyncio.sleep(0.01)

    async def _async_init_websocket(self):
        async with websockets.serve(self.ws_page_distributor_handler, "", self.ws_port, ssl=self._ws_ssl_context):
            await self._async_while_not_stopped()

    def _init_websocket(self):
        asyncio.run(self._async_init_websocket())

    def run(self):
        """
        Run loop of the manager monitor.
        Endless loop, only returns with exception.
        :return:
        """
        self._websocket_thread = threading.Thread(target=self._init_websocket)
        self._websocket_thread.start()

        try:
            self._run()
        except Exception as e:
            self._should_stop = True
            logger.critical("got some exception... telling websocket thread to stop")
            self._websocket_thread.join(10)
            logger.critical("websocket thread stopped. destroy manager monitor")
            self.destroy()
            logger.exception(e)
            raise e

    def _run(self):
        """
        Run loop of the manager monitor.
        Endless loop, only returns on exception.
        :return:
        """
        # create time dependent functions
        push_fn = make_do_in_interval_fn(self.push_results, self.push_interval_s, time.time())
        update_available_tabs_fn = make_do_in_interval_fn(self.update_tabs, self.update_tabs_interval_s)
        simulate_activity = make_do_in_interval_fn(self.simulate_activity, self.simulate_activity_interval_s)
        check_and_handle_health_status = make_do_in_interval_fn(self.check_and_handle_drm_health_status,
                                                                self.health_check_interval_s)

        # while function will execute all the functions the first time in the provided order,
        #   but each only if the remaining wait interval has been reached.
        #   Thus, the order could become arbitrary, depending on the intervals.
        # However, the loop will never execute two functions simultaneously and the wait condition will always only
        # wait as long until the next function is to be executed.
        while True:
            wait_until_s = update_available_tabs_fn()[1]

            wait_until_s = min(check_and_handle_health_status()[1], wait_until_s)

            wait_until_s = min(simulate_activity()[1], wait_until_s)

            # may report the difference if necessary
            # if diff < 0:
            #     logger.debug(f"waiting took {-diff} longer than expected")

            # push data to database every push_interval_s
            wait_until_s = min(push_fn()[1], wait_until_s)

            # non-busy wait
            to_wait_s = wait_until_s - time.time()
            if to_wait_s > 0:
                logger.debug(f"wait remaining wait time... {to_wait_s}s")
                time.sleep(to_wait_s)

    def simulate_activity(self):
        """
        Simulate the activity of all the pages, e.g., by briefly setting them into focus.
        :return:
        """
        logger.info("simulate activity...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.driver_managers)) as executor:
            futures = dict()
            # start threads
            for i in self.driver_managers:
                futures.update({executor.submit(self.driver_managers[i].simulate_activity): i})

            # wait for results
            for future in concurrent.futures.as_completed(futures):
                index = futures[future]
                try:
                    _ = future.result(60)
                except Exception as exc:
                    logger.error(f"driver manager with index {index} generated an exception:\n", exc)
                    raise exc

    def update_tabs(self):
        """
        Update the browser instances with its available tabs.
        Takes first available driver manager with an open page, refreshes it and retrieve tabs.
        If no page is open, opens the first page with first driver manager.
        :return:
        """
        logger.info("update available tabs")

        # compute which urls we already have being monitored
        got_monitored_urls = []
        for i in self.driver_managers:
            drm = self.driver_managers[i]
            got_monitored_urls += list(drm.page_managers.keys())

        got_monitored_urls = set(got_monitored_urls)

        # urls which we require
        required_monitored_urls = {"https://rbnbr.github.io/random-signal"}

        # self.compute_required_urls()
        # required_monitored_urls.update(self.required_urls)  # not implemented

        # close got monitored urls that are not required (anymore?)
        to_close_urls = list(got_monitored_urls.difference(required_monitored_urls))
        for i in self.driver_managers:
            drm = self.driver_managers[i]
            with drm:
                drm.remove_monitor_urls(to_close_urls)

        # find missing urls and distribute to drms
        required_monitored_urls.difference_update(got_monitored_urls)
        missing_monitored_urls = list(required_monitored_urls)

        # distribute to drms
        for url in missing_monitored_urls:
            # get drm with least urls
            drm_i = sorted(range(len(self.driver_managers)),
                           key=lambda k: len(self.driver_managers[k].page_managers))[0]

            drm = self.driver_managers[drm_i]

            # find suitable spm
            spm_class = None
            for spm in SPM_Classes:
                if url.startswith(spm.BASE_URL):
                    spm_class = spm

            if spm_class is None:
                raise NotImplementedError(f"no spm found for url: {url}")

            drm.add_single_page_monitor(spm_class(drm=drm, page_url=url), True)

    def push_results(self):
        """
        Push drm results.
        :return:
        """
        logger.debug("collect latest drm results")
        latest_page_results = self.collect_latest_drm_results()

        # filter signal results
        signal_results = {page_url: latest_page_results[page_url] for page_url in latest_page_results
                             if latest_page_results[page_url]["page_monitor_class"] is RandomSignalSPM}

        # handle signal results
        # try:
        #     with self.postgres_connection.cursor() as cur:
        #         # count_pushed_signals = self._push_signal_results(cur, signal_results)  # Not implemented
        #         count_pushed_signals = 0
        #         self.postgres_connection.commit()
        #         logger.info(f"pushed {count_pushed_signals} many signals")
        # except Exception as e:
        #     logger.error("got error during push of spm_results: " + str(e))
        #     self.postgres_connection.rollback()

    def report_drm_health_status(self):
        """
        Reports the last drm health status
        :return:
        """
        health_status = dict()
        for i in self.driver_managers:
            drm = self.driver_managers[i]
            health_status.update(drm.report_health_status())

        return health_status

    def collect_latest_drm_results(self) -> dict:
        """
        Pull the drm results from their individual pages and return them.
        :return: A mapping {"page_url": {"page_data": page_data, "page_monitor_class": page.__class__}}
        """
        page_results = dict()

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.driver_managers)) as executor:
            futures = dict()
            # start threads
            for i in self.driver_managers:
                futures.update({executor.submit(self.driver_managers[i].pull_latest_measurements): i})
            # wait for results
            for future in concurrent.futures.as_completed(futures):
                index = futures[future]
                try:
                    page_result = future.result(60)
                    page_results.update(page_result)

                except Exception as exc:
                    logger.error(f"driver manager with index {index} generated an exception:\n", exc)
                    raise exc

        return page_results

    def make_remote_driver_managers(self, n_instances: int, headless: bool = False,
                                    headless_first_override: bool = None, max_time_for_retries_s: int = 60):
        """
        Creates the amount of remote driver manager instances and returns them as a dict with their index as key.
        :param max_time_for_retries_s: Tries to make the remote drivers. Retries until max_time_for_retries_s
            has been reached, then raises exception.
        :param headless_first_override:
        :param headless:
        :param n_instances:
        :return:
        """
        start_s = time.time()

        driver_managers = dict()

        addresses = self.get_addresses()

        ff_profile_path = get_env_non_empty("PYAPP_FIREFOX_PROFILE_DIR",
                                            default="firefox_profiles/ff-profile.WithCACertificate")
        ff_profile_path = pathlib.Path(ff_profile_path)

        use_profile = ff_profile_path.exists() and ff_profile_path.is_dir()

        if not use_profile:
            logger.info(f"not using firefox profile as it doesn't exist or is not a dir... "
                        f"got profile path: {ff_profile_path}")
        else:
            logger.info(f"using firefox profile at path: {ff_profile_path}")

        for i in range(n_instances):
            logger.info(f"trying to connect to instance num {i}: {addresses[i]}")
            command_executor = addresses[i]

            firefox_options = FirefoxOptions()

            if use_profile:
                # firefox_options.set_preference("profile", str(ff_profile_path))
                firefox_options.profile = str(ff_profile_path)

            if headless_first_override is not None and i == 0:
                firefox_options.headless = headless_first_override
            else:
                firefox_options.headless = headless

            ok = False
            while max_time_for_retries_s > time.time() - start_s:
                ok = False
                try:
                    driver_managers[i] = DriverManager(command_executor=command_executor, options=firefox_options)
                    ok = True
                    break
                except (urllib3.exceptions.MaxRetryError, urllib3.exceptions.ProtocolError):
                    logger.info(f"failed to connect to instance {i}, try again in 5s")
                    time.sleep(5)
            if not ok:
                raise RuntimeError(f"failed to connect to all instances in over {max_time_for_retries_s}s")

        return driver_managers

    def destroy(self):
        """
        Destroys all driver managers.
        :return:
        """
        self._should_destroy = True
        self._should_stop = True

        for i in self.driver_managers:
            drm = self.driver_managers[i]

            drm.destroy()

        self.driver_managers.clear()

    def check_and_handle_drm_health_status(self):
        logger.debug("check and handle health status")
        health_status = self.report_drm_health_status()

        timestamp = time.time()
        only_health_status = {url: (health_status[url]["health_status"], timestamp) for url in health_status}

        # add health status to list
        append_element_dict_to_list_dict(self.health_stati, only_health_status)

        fail = False

        # check if any page has more than allowed negative health stati in the specified last interval
        max_found_not_ok = 0
        max_found_not_ok_url = "none"
        for url in self.health_stati:
            # remove health stati older than allowed
            self.health_stati[url] = sorted(list(filter(
                lambda hs_ts: timestamp - hs_ts[1] <= self.MAX_PAGE_UNHEALTHY_COUNT_AGE_S,
                self.health_stati[url])),
                key=lambda hs_ts: hs_ts[1])
            not_ok_health_status = list(filter(lambda hs_ts: not hs_ts[0], self.health_stati[url]))

            # set not ok health status to page
            health_status[url]["page_manager"].set_unhealthy_count(len(not_ok_health_status))

            if len(not_ok_health_status) >= max_found_not_ok:
                max_found_not_ok = len(not_ok_health_status)
                max_found_not_ok_url = url
            if len(not_ok_health_status) > self.MAX_PAGE_UNHEALTHY_REFRESH_IN_TIME_LIMIT:
                logger.critical(f"page with url {url} has {len(not_ok_health_status)} unhealthy reports. application "
                                f"will fail")
                fail = True

        logger.info(f"the maximum of unhealthy refreshs in the last {self.MAX_PAGE_UNHEALTHY_COUNT_AGE_S}s was "
                    f"{max_found_not_ok} from page {max_found_not_ok_url}, "
                    f"allowed are {self.MAX_PAGE_UNHEALTHY_REFRESH_IN_TIME_LIMIT}")

        if not fail:
            # warn about unhealthy pages
            total = len(only_health_status)
            ok_pages = list(filter(lambda url: only_health_status[url][0], only_health_status))
            ok = len(ok_pages)
            not_ok_pages = list(filter(lambda url: not only_health_status[url][0], only_health_status))
            not_ok = len(not_ok_pages)

            if not_ok > 0:
                logger.warning(f"detected not healthy page managers: last health status: total: {total}, "
                               f"ok: {ok}, "
                               f"not_ok: {not_ok}; refresh not ok page managers: {not_ok_pages}")

            # refresh pages that were unhealthy
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.driver_managers)) as executor:
                futures = dict()
                # start threads
                for i in self.driver_managers:
                    futures.update({executor.submit(self.driver_managers[i].refresh_urls,
                                                    not_ok_pages): i})

                # wait for results
                for future in concurrent.futures.as_completed(futures):
                    index = futures[future]
                    try:
                        _ = future.result(2 * len(list(health_status.keys())))
                    except Exception as exc:
                        logger.error(f"driver manager with index {index} generated an exception:\n", exc)
                        raise exc

            page_with_biggest_refresh_count = max(map(lambda drm_i: max(
                self.driver_managers[drm_i].page_managers.values(), key=lambda p: p.get_total_refresh_count()),
                                                      self.driver_managers), key=lambda p: p.get_total_refresh_count())

            logger.info(
                f"the current total refresh count among all pages is {SinglePageMonitoring.TOTAL_REFRESH_COUNT}"
                f", the page with the highest refresh count is {page_with_biggest_refresh_count.page_url} with"
                f" a refresh count of {page_with_biggest_refresh_count.get_total_refresh_count()}")

        else:
            logger.critical("detected repeated unhealthy page manager: "
                            "closing program with -101 to investigate the error")
            self.destroy()
            exit(-101)
