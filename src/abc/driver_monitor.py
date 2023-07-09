from selenium import webdriver

from src.abc.remote_driver_monitor import RemoteDriverManager
from src.abc.single_page_monitoring import SinglePageMonitoring


class DriverManager(RemoteDriverManager):
    """
    A remote driver manager extended to handle multiple pages.
    """

    def __init__(self, command_executor: str,
                 *, options: webdriver.FirefoxOptions = None):
        super().__init__(command_executor=command_executor, options=options)

        self.page_managers = dict()

        self.default_page = SinglePageMonitoring(self, "about:logo")
        self.default_page.refresh_page()

        self._should_destroy = False

    def simulate_activity(self):
        """
        Simulate the activity of all its pages, e.g., by briefly setting them into focus.
        :return:
        """
        for url in self.page_managers:
            with self.page_managers[url] as pm:
                pm.simulate_activity()

    def destroy(self):
        """
        Destroys all page managers, then quit the driver.
        :return:
        """
        self._should_destroy = True

        for url in self.page_managers:
            page = self.page_managers[url]
            page.destroy()

        self.page_managers.clear()
        super().destroy()

    def refresh_urls(self, urls: list):
        """
        refreshs the pages belonging to the provided urls provided that they are being monitored from this drm
        :param urls:
        :return:
        """
        for url in urls:
            if self.is_monitoring_url(url):
                with self.page_managers[url] as page:
                    page.refresh_page()

    def is_monitoring_url(self, url: str):
        return url in self.page_managers
        # or url in map(lambda pm: self.page_managers[pm].redirect_url, self.page_managers)

    def add_single_page_monitor(self, single_page_monitoring: SinglePageMonitoring,
                                with_refresh: bool = False):
        """
        Adds a single page monitor with a specific url to monitor and loads them.
        If url is already being monitored: do nothing (or refresh). It keeps the previous page monitor.
        If url is not there: add SinglePageMonitoring for this url.

        Adding does not automatically load the page or refresh it if not activated.
        :param with_refresh:
        :param single_page_monitoring:
        :return:
        """
        url = single_page_monitoring.page_url

        if self.is_monitoring_url(url):
            if with_refresh:
                with self.page_managers[url] as page:
                    page.refresh()
        else:
            self.page_managers[url] = single_page_monitoring
            if with_refresh:
                with self.page_managers[url] as page:
                    if page.status != SinglePageMonitoring.COMPLETE:
                        page.refresh()  # probably never called since 'with' calls it already

    def remove_monitor_urls(self, to_remove_urls: list):
        """
        Removes a page from being monitored and closes it.
        :param to_remove_urls:
        :return:
        """
        for url in to_remove_urls:
            if not self.is_monitoring_url(url):
                continue
            else:
                self.page_managers[url].destroy()
                del self.page_managers[url]

    def clear_monitor_urls(self):
        self.remove_monitor_urls(list(self.page_managers.keys()))

    def report_health_status(self):
        """
        Report health status of all sites that are to be handled.
        :return:
        """
        return {url: {
            "url": url,
            "page_manager": self.page_managers[url],
            "health_status": self.page_managers[url].is_healthy()
        } for url in self.page_managers}

    def pull_latest_measurements(self) -> dict:
        """
        Pulls the page data of all pages that was collected since last call to their pull_page_data() method
        and returns them.
        :return: Mapping {"page_url": {"page_data": page_data, "page_monitor_class": page.__class__}}
        """
        all_page_data = dict()
        for url in self.page_managers:
            with self.page_managers[url] as page:
                page_data = page.pull_page_data()
                all_page_data[url] = {
                    "page_data": page_data,
                    "page_monitor_class": page.__class__
                }

        return all_page_data
