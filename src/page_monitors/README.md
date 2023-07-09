# Page Monitors

The page monitors here should inherit of SinglePageMonitoring.
They are supposed to define how to monitor one type of specific page, i.e., pages that have the same layout and the same information extraction approaches can be used.
A page monitor class has its corresponding injection script which defines the data the page monitor receives.

Page monitor instances can differ in their url, e.g. via url or query parameters, though they still expect the same layout from the webpage.
Each page monitor instance is responsible for one specific url.
