import threading
import time
import websockets
import asyncio
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver import FirefoxOptions


# allow firefox insecure websocket connection from https site
firefox_options = FirefoxOptions()
firefox_options.set_preference('network.websocket.allowInsecureFromHTTPS', True)

driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=firefox_options)


# Step 1: Leverage Selenium (or other software to control a browser) to open the live updated webpage to monitor
target_url = "https://rbnbr.github.io/random-signal"
driver.get(target_url)

# Step 2: Run a WebSocket server which should collect and further process the data
websocket_port = 8001
stop = False


async def websocket_callback(websocket):
    print("waiting for messages")
    async for message in websocket:
        print(message)


async def _run_websocket():
    async with websockets.serve(websocket_callback, "", websocket_port, ssl=None):
        while not stop:
            await asyncio.sleep(0.01)


def ws_thread():
    asyncio.run(_run_websocket())


thread = threading.Thread(target=ws_thread)
thread.start()


# Step 3: Inject JavaScript to the webpage via, e.g., Selenium (step 1) which does the following:
# a) Create a WebSocket object and open a connection to the WebSocket Server (from step 2)
# b) Create MutationObserver object(s) to monitor the data to be retrieved, with a callback,
#   which sends the new data to the WebSocket
injection_script = """
function createWebsocket(url) {
    window._myWebSocket = new WebSocket(url);

    return window._myWebSocket;
}

function parseValue(value_string) {
    let v = value_string.slice(value_string.search(':')+1).replace(' ', '');
    return +v;
}

function parseTimeStamp(timestamp_string) {
    let ts = timestamp_string.slice(timestamp_string.search(':')+1).replace(' ', '');
    let [hms, ms] = ts.split('.');
    let [h, m, s] = hms.split(':');

    let d = new Date();
    d.setHours(+h, +m, +s, +ms);

    return d.toISOString();
}

function makeCallback(h1, h2, websocket, page_url) {
    let h1_ = h1;
    let h2_ = h2;
    let ws = websocket;
    function callback(mutationList, observer){
        console.log(h1_.innerHTML, h2_.innerHTML);

        const signal_result = {
            page_url: page_url,
            signal_element: {
                timestamp: parseTimeStamp(h2_.innerText),
                value: parseValue(h1_.innerText)
            }
        }

        ws.send(JSON.stringify(signal_result));
    }

    return callback;
}

function createMutationObserver(websocket, page_url) {
    let div = document.getElementById("signal");

    let h1 = div.getElementsByTagName("h1")[0];
    let h2 = div.getElementsByTagName("h2")[0];

    // create mutation observers for the value and timestamp
    window._myMutationObserver = {
        observer: new MutationObserver(makeCallback(h1, h2, websocket, page_url)),
        target: h1,
    };

    return window._myMutationObserver;
}

function setup(pyapp_url, page_url) {
    const ws = createWebsocket(pyapp_url);
    let mutationObserver = createMutationObserver(ws, page_url);

    const config = { characterData: true, subtree: true };

    // start observing
    mutationObserver.observer.observe(mutationObserver.target, config);
}

setup(arguments[0], arguments[1]);
"""

time.sleep(2)  # wait for websocket server to fully start
driver.execute_script(injection_script, f"ws://127.0.0.1:{websocket_port}", target_url)

# Step 4: Process the data in the application, e.g., by aggregating specific values and storing them in a database
# Skipped as we don't save the data
time.sleep(10)
stop = True
driver.quit()
thread.join(10)
