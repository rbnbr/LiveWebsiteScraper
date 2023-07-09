import logging
from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import InvalidSessionIdException


logger = logging.getLogger("scraper_logger")


class RemoteDriverManager:
    """
    This class manages one remote selenium driver that corresponds to one single browser instance.
    It connects to remote browser, handles crashes and reconnects.

    TOOD: Fix bugs. Crashes are not correctly handled.
    """
    # holds the current active driver, i.e., the last driver that used "with".
    # also prevents two drivers to have nested "with"
    _CURRENT_ACTIVE_PAGE = None

    def __init__(self, command_executor: str, options: webdriver.FirefoxOptions = None):
        assert command_executor != "", "got empty command executor string"
        self.command_executor = command_executor

        if options is None:
            self._options = webdriver.FirefoxOptions()
        else:
            self._options = options

        self.driver: WebDriver = None
        self.session_id = ""

        # to check if enter was successful
        self._is_in_context = False

        self._should_destroy = False
        self._is_destroyed = False

    def destroy(self):
        """
        Quits the current driver
        :return:
        """
        if self._is_destroyed:
            return
        self._should_destroy = True

        if self.driver is not None:
            self.driver.quit()
            self.driver = None
        self._is_destroyed = True

    @staticmethod
    def attach_to_session(executor_url: str, session_id: str):
        original_execute = WebDriver.execute

        def new_command_execute(self, command, params=None):
            if command == "newSession":
                # Mock the response
                return {'success': 0, 'value': None, 'sessionId': session_id}
            else:
                return original_execute(self, command, params)

        # Patch the function before creating the driver object
        WebDriver.execute = new_command_execute
        driver = webdriver.Remote(command_executor=executor_url)
        driver.session_id = session_id

        # Replace the patched function with original function
        WebDriver.execute = original_execute

        return driver

    def print_session_id(self):
        return f"'{self.session_id[:8]}...'"

    def _connect_to_remote(self):
        return webdriver.Remote(command_executor=self.command_executor, options=self._options)

    def __enter__(self):
        if self is self._CURRENT_ACTIVE_PAGE:
            return

        if self._CURRENT_ACTIVE_PAGE is not None:
            raise RuntimeError("cannot use the context of two page object simultaneously")

        if self.driver is None and not self._should_destroy:
            if self.session_id == "":
                logger.debug("trying to connect to new remote driver session")
                self.driver = self._connect_to_remote()
                self.session_id = self.driver.session_id
                logger.info(f"connected to remote: {self.command_executor} and new session id: "
                         f"{self.print_session_id()}")
            else:
                try:
                    logger.debug("trying reconnect to existing session")
                    self.driver = self.attach_to_session(self.command_executor, self.session_id)
                    logger.info(f"reconnected to existing remote session at {self.command_executor} with id "
                             f"{self.print_session_id()}")
                except InvalidSessionIdException as e:
                    logger.error(f"couldn't reconnect to existing session with error: {e}..\n"
                              f"trying to create new session instead")
                    self.driver = self._connect_to_remote()
                    self.session_id = self.driver.session_id
                    logger.info(f"connected to remote: {self.command_executor} and new session id: "
                             f"{self.print_session_id()}")
        else:
            if self.driver is not None:
                assert self.session_id != "", f"session id is empty but driver is not None"
                #logger.debug(f"reusing existing driver at {self.command_executor} with session id: "
                #          f"{self.print_session_id()}")

        self._is_in_context = True

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error("exited with exception, setting driver to None, exception:\n" + str(exc_type) + "\n" + str(exc_val))
            print(exc_tb)
            self.driver = None
            self.session_id = ""  # TODO: only do this if necessary

        self._is_in_context = False

        # TODO: handle different types of exception (may need to reset session as well)




