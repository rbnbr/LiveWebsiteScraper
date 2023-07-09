import logging
import time

import selenium.common
from selenium import webdriver
from selenium.common import NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.by import By

from src.util import get_env_non_empty
from src.abc.remote_driver_monitor import RemoteDriverManager
from selenium.webdriver.common.window import WindowTypes


logger = logging.getLogger("scraper_logger")

PYAPP_ADDR = get_env_non_empty("PYAPP_ADDR", "live-data-scraper")
WS_PORT = get_env_non_empty("WS_PORT", 8001)


class SinglePageMonitoring:
    WINDOW_TYPE = WindowTypes.TAB

    UNINITIALIZED = 'uninitialized'
    LOADING = 'loading'
    COMPLETE = 'complete'

    REFRESH_TIMEOUT_S = 2  # calling refresh only has an effect if waiting this time

    TOTAL_REFRESH_COUNT = 0  # total refresh count among all single page monitors

    # holds the current active page, i.e., the last page that used "with". also prevents two pages to have nested "with"
    _CURRENT_ACTIVE_PAGE = None

    BASE_URL = "undefined"  # base url (used by monitor manager to find suitable spm)

    """
    This class is responsible to monitor a single page.
    It handles loading, refreshes, and information retrieval.
    Collects information about the status of the page, i.e., whether information is still continuously updated or a 
        restart is required.
    """
    def __init__(self, drm: RemoteDriverManager, page_url: str):
        assert drm is not None, "driver manager is None"
        assert page_url != "", "page url is empty"

        self.drm: RemoteDriverManager = drm
        self.page_url: str = page_url
        self.redirect_url: str = page_url
        self.window_handle: str = ""
        self.status = self.UNINITIALIZED

        self._last_refresh_s = 0

        self._total_refresh_count = 0

        self.unhealthy_count = 0

        # to check if enter was successful
        self._is_in_context = False

        self._should_destroy = False
        self._is_destroyed = False

    def set_unhealthy_count(self, count: int):
        self.unhealthy_count = count

    def __enter__(self):
        if self is self._CURRENT_ACTIVE_PAGE:
            return

        if self._CURRENT_ACTIVE_PAGE is not None:
            raise RuntimeError("cannot use the context of two page object simultaneously")

        if self._should_destroy:
            return

        if self.window_handle != "":
            with self.drm as drm:
                drm.driver.switch_to.window(self.window_handle)

                # check if url still matches
                if not drm.driver.current_url.startswith(self.page_url) and \
                        not drm.driver.current_url.startswith(self.redirect_url):
                    self.refresh_page()
        else:
            self.refresh_page()

            with self.drm as drm:
                drm.driver.switch_to.window(self.window_handle)

        self._is_in_context = True

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._is_in_context = False
        pass

    def get_total_refresh_count(self):
        return self._total_refresh_count

    @staticmethod
    def accept_check(dr: webdriver.Firefox):
        """
        Performs the accept check.
        :param dr:
        :return:
        """
        try:
            acc = dr.find_elements(By.CLASS_NAME, "accept")
            if len(acc) > 0 and acc[0].is_displayed():
                acc[0].click()
        except NoSuchElementException as e:
            pass
        except ElementNotInteractableException as e:
            pass

    def after_refresh_callback(self, driver: webdriver.Firefox):
        """
        Is called during refresh_page() after the page has been loaded if it is not a default page
        :return:
        """
        return

    def refresh_page(self):
        """
        Opens a new window and updates the current window handle.
        Then closes the previous window.
        Loads the page_url in the new window.
        :return:
        """
        if time.time() - self._last_refresh_s < self.REFRESH_TIMEOUT_S:
            return

        with self.drm as drm:
            driver = drm.driver

            self.status = self.UNINITIALIZED

            # open new tab
            driver.switch_to.new_window(self.WINDOW_TYPE)
            new_handle = driver.current_window_handle

            # switch back and close and switch back
            if self.window_handle != "":
                driver.switch_to.window(self.window_handle)
                driver.close()
                driver.switch_to.window(new_handle)

            # update window handle
            self.window_handle = new_handle

            # load page
            self.status = self.LOADING
            driver.get(self.page_url)

            # if not default page
            if self.page_url != "about:logo":
                self.accept_check(driver)

                self.after_refresh_callback(driver)

            self.redirect_url = driver.current_url

            self.status = self.COMPLETE
            self._last_refresh_s = time.time()

            self._total_refresh_count += 1
            SinglePageMonitoring.TOTAL_REFRESH_COUNT += 1

    def close(self):
        try:
            with self.drm as drm:
                assert drm.driver.current_url.startswith(self.page_url) or \
                   drm.driver.current_url.startswith(self.redirect_url), \
                   "current driver's url does not match page url, did you use 'with page'"
                drm.driver.close()
                drm.driver.switch_to.window(drm.default_page.window_handle)
        except selenium.common.WebDriverException:
            pass
        finally:
            self.window_handle = ""
            self.status = self.UNINITIALIZED
            self.redirect_url = ""

    def destroy(self):
        if self._is_destroyed:
            return
        self._should_destroy = True
        self.close()
        self.drm = None
        self._is_destroyed = True
        # self._page_data_history.clear()
        # self._prev_wkn_elements.clear()

    def simulate_activity(self):
        # with self.drm as drm:
        #     drm.driver.execute_script("setTimeout(() => scroll(0, 250), 10); "
        #                               "setTimeout(() => scroll(0, 0), 1000);")
        return  # scrolling might not be necessary. the bug could be somewhere else

    def get_page_source(self):
        with self.drm:
            return self.drm.driver.page_source

    def is_healthy(self) -> bool:
        """
        Returns if the site is healthy.
        To be overridden. Otherwise, returns always True.
        :return:
        """
        return True

    def pull_page_data(self) -> dict:
        """
        Returns the currently available page data and deletes the returned result.
        To be overridden. Otherwise, returns empty dict
        :return:
        """
        return dict()

    def add_page_data(self, o: dict):
        """
        Call this method to update and add this object for this page.
        To be overridden. Otherwise, does nothing.
        :param o:
        :return:
        """
        return
