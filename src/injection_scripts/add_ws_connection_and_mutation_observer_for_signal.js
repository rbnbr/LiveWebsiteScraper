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
