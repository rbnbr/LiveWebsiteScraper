import logging
import time

import dateutil.tz

from src.data_elements.signal_element import SignalElement
from src.abc.single_page_monitoring import SinglePageMonitoring, PYAPP_ADDR, WS_PORT
from src.abc.driver_monitor import RemoteDriverManager
from src.util import read_file_content, parse_timestamp, get_env_non_empty
from dateutil.parser import ParserError


logger = logging.getLogger("scraper_logger")

timezone_berlin = dateutil.tz.gettz("Europe/Berlin")


class RandomSignalSPM(SinglePageMonitoring):
    """
    Class to monitor a single page of a random signal: https://rbnbr.github.io/random-signal
    """
    # maximum time we can go without new data registered to still be healthy
    #   (example tailored to https://rbnbr.github.io/random-signal but translatable to other sites)
    SPM_PAGE_DATA_MAX_TIME_SINCE_LAST_CHANGE_S = float(
        get_env_non_empty("SPM_PAGE_DATA_MAX_TIME_SINCE_LAST_CHANGE_S", default=10))

    BASE_URL = "https://rbnbr.github.io/random-signal"

    def __init__(self, drm: RemoteDriverManager, page_url: str):
        super().__init__(drm=drm, page_url=page_url)
        self._signal_data = dict()

        self._last_signal_time_s = 0

        self._zero_signal_change_warning = False

        # factors on time to wait to call unhealthy before calling it again
        # if factor == 1, then it is equal to SPM_PAGE_DATA_MAX_TIME_SINCE_LAST_CHANGE_S
        # NOTE: if the time_factors become bigger than the max duration in the monitor manager, than it will never fail
        self._time_wait_factors = [1, 1, 2, 5, 10]

    @staticmethod
    def make_key(signal_element: SignalElement) -> str:
        return f"ts: '{signal_element.timestamp.isoformat()}'"

    def after_refresh_callback(self, driver):
        # execute script for observing signal
        script_content = read_file_content("./src/injection_scripts/"
                                           "add_ws_connection_and_mutation_observer_for_signal.js")
        driver.execute_script(script_content, f"wss://{PYAPP_ADDR}:{WS_PORT}", self.page_url)

    def destroy(self):
        super().destroy()
        self._signal_data.clear()

    @staticmethod
    def _is_healthy(last_refresh_s: float, last_signal_time_s: float,
                    max_elapsed_time_since_last_signal_s: float) -> bool:
        t = time.time()

        if t - last_refresh_s >= max_elapsed_time_since_last_signal_s:
            healthy = t - last_signal_time_s < max_elapsed_time_since_last_signal_s
        else:
            healthy = True

        return healthy

    def is_healthy(self) -> bool:
        # is healthy if the last signal change was less than 10 seconds ago
        time_to_wait_s = self._time_wait_factors[min(self.unhealthy_count,
                                                     len(self._time_wait_factors) - 1)] * \
                          self.SPM_PAGE_DATA_MAX_TIME_SINCE_LAST_CHANGE_S

        healthy = self._is_healthy(self._last_refresh_s, self._last_signal_time_s, time_to_wait_s)

        if not healthy:
            logger.warning(f"page with url '{self.redirect_url}' reported not healthy with last signal being "
                           f"over {self.SPM_PAGE_DATA_MAX_TIME_SINCE_LAST_CHANGE_S}s in the past: "
                           f"{time.time() - self._last_signal_time_s}")

        return healthy

    def pull_page_data(self) -> dict:
        """
        Returns the currently available page data and deletes the returned result.
        :return:
        """
        num_elements = len(self._signal_data)

        # trigger warning if no data is available
        if num_elements == 0 and not self._zero_signal_change_warning:
            # logger.warning(f"page {self.page_url} did not return any new signal since the "
            #                f"last pull_page_data call. this warning is only "
            #                f"triggered once until new signal values are again returned")
            # NOTE: skipped zero elements warning due to higher smaller pull rate
            self._zero_signal_change_warning = True
        else:
            self._zero_signal_change_warning = False

        ret = self._signal_data.copy()
        self._signal_data.clear()
        return ret

    def add_page_data(self, signal_json: dict):
        """
        Call this method to update and add new signal elements for this page.

        :param signal_json: contains the signal element
        :return:
        """
        # parse signal value and add
        try:
            timestamp = parse_timestamp(signal_json["timestamp"])
            timestamp = timestamp.replace(tzinfo=timezone_berlin)
        except ParserError:
            # timestamp = None
            logger.warning(f"got signal with error parsing timestamp from page '{self.page_url}... "
                           f"skip signal: {signal_json}")
            return

        signal_value = int(float(''.join(filter(lambda c: c in "1234567890", signal_json["value"]))))

        signal_element = SignalElement(timestamp=timestamp, value=signal_value)

        k = self.make_key(signal_element)
        self._signal_data[k] = signal_element
        self._last_signal_time_s = max(self._last_signal_time_s, int(signal_element.timestamp.timestamp()))
        # logger.debug(f"added signal element: {signal_element}")
