# Live Website Scraper

An exemplary implementation of how to do webscraping for websites that display fast-changing data which cannot be accessed by e.g., a direct websocket connection to their API, but which' retrieval requires the active monitoring of the website.
This repository proposes an exemplary implementation of a solution to this problem using Python and Selenium.

#### Note
The code and the concepts used in this repository stem originally from another bigger project, and may contain some artifacts from it.
I tried to prune it to contain only some of the core principles and utilities which should be generalizable for arbitrary websites.

Be aware that some concepts and ideas I had are probably not sufficiently implemented, and also may still contain bugs.
Please feel free to suggest improvements via pull requests or issues.

For now, this repository does not serve as a library or package to be imported, but as an example that has to be adjusted for new use cases.

## Concept
In contrast to the standard data scraping approaches described in the web which usually rely on regular pulling intervals to retrieve mostly static data from a website, this concept focuses on dynamic websites which live updates.
The idea is that changes in the website are actively monitored and new data is directly being pushed to the application via an open connection instead of being pulled by it.

There are four steps involved:
1. Leverage Selenium (or other software to control a browser) to open the live updated webpage to monitor.
2. Run a WebSocket server which should collect and further process the data
3. Inject JavaScript to the webpage via, e.g., Selenium (step 1) which does the following:
   - Create a WebSocket object and open a connection to the WebSocket Server (from step 2)
   - Create MutationObserver object(s) to monitor the data to be retrieved, with a callback, which sends the new data to the WebSocket
6. Process the data in the application, e.g., by aggregating specific values and storing them in a database.

In general, it is quite simple and its implementation here is much more complex than necessary, which is due to the projects' origin as described above.

A minimal example of this concept can be found here: [minimal_example.py](./minimal_example.py).

The steps to run the minimal example are the following:
````
pip install webdriver-manager selenium websockets
python minimal_example.py
````

You may use and adjust the minimal example as required.
Alternatively, you may also try to run the provided project which already implements additional features for more robustness and the management of many tabs.


## Additional Features Of The Provided Project
The project contains additional utilities that I use in the original project:
- Classes which try to abstract from the selenium driver object to..
  - Handle individual pages
  - Handle individual remote selenium instances (which in itself handle multiple pages)
  - Handle multiple drivers
- A run loop to
  - Update tabs (in case some tabs were closed unexpectedly, or the webpages we want to monitor depend on other dynamic factors, conditions, ...)
  - Check health status of pages (and issue page refresh if unhealthy)
  - Simulate activity
  - Bundle collected data and commonly process it by, e.g., pushing it to a database

## Running The Project
The current project collects artificial data from my github.io page: [https://rbnbr.github.io/random-signal](https://rbnbr.github.io/random-signal).
You can run the project via docker compose: ``docker compose up`` (optionally ``-d``).

The docker compose file also expects two secrets, though, since they are not leveraged at the moment, it is enough to create two empty files in the appropriate location for that:
```
mkdir secure
mkdir secure/tls-ssl
echo "" > secure/postgres_credentials.txt
echo "" > secure/tls-ssl/cert.key
```

If you want to run it locally, make sure to set the environment variables accordingly.
See the settings in the [docker-compose.yml](./docker-compose.yml) and [Dockerfile](./Dockerfile) for a description of the environment variables.

Some settings are also configured via the configuration files [default_config.json](./default_config.json) and [default_debug_config.json](./default_debug_config.json).

## Adjusting The Project
To adjust the project to monitor a different website you most likely have to do the following steps:
- Create a new page monitor that handles opening the website (page), refresh actions, health check, simulate activity, and first processing of the incoming data.
  You may use the existing [RandomSignalPageMonitor](./src/page_monitors/random_signal_spm.py) as reference.
- Create a new injection script corresponding to the new website layout and the data format the page monitor expects.
  You may use the existing [RandomSignalInjectionScript](./src/injection_scripts/add_ws_connection_and_mutation_observer_for_signal.js) for reference.
- If necessary, create a new data element for structured access to the data sent, see example [SignalElement](./src/data_elements/signal_element.py).
- Adjust the [monitor manager](./src/abc/monitor_manager.py) (or inherit) to open the correct tabs by updating (or overriding) the ``update_tabs`` method.
  - Also configure the ``push_results`` method accordingly to handle the new type of data from the new page manager.

