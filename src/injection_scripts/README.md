# Injection Scripts

Each injection script belongs to one type of page monitor.
They are usually injected in the after_refresh_callback(..) method and have the following purposes:
- create the websocket connection to the websocket server which should receive data (here, the same host as the python application is running on)
- find the DOM elements of the website to be monitored
- create the MutationObserver object with appropriate configuration to listen to changes
- pre-process the data and send it to the websocket
  - here:
    - the data is always sent as JSON object containing the page_url of the page monitor
    - the rest of the object should be coherent with what the page monitor expects in its add_page_data(...) method

