i have an extensive set of youtube bookmarks in my firefox browser, added over a long period of time. Currently they are "out of sight, out of mind". I want to be able to surface them more readily so that I can rediscover videos i have forgotten about or haven't watched in a while. I'd like a web interface that shows me all my youtube bookmarks, with a summary of each one. Also show me the number of times each page has been viewed, the date the link was added, and the date it was last viewed. I want to be able to sort asc or desc by any of those attributes. If possible I also want to be able to group them by youtube channel/creator. I will also want to choose a grouping by keywords like "guitar tutorials" or "thai food recipes" 

There can be two parts so that we don't have to scrape the link every time the web interface is accessed. 1. a web crawler script to get the details from the local bookmarks file and store the details in a separate local datastore, and 2. a web interface that can read from the local datastore and present a clean user friendly web interface to that data. 

I want the implementation language to be python.
I want you to use a test-driven approach. Write the test first before implementation, make sure it fails, then write the implementation  and make sure it passes before calling the functionality complete.

For the web crawler, I want to run it from the command line with arguments to indicate the location of the input file (firefox bookmarks) and another one to specify the output file.
For the web interface, I am okay running it locally for now. The script to run it should have a way to point to the local storage file.

create a separate plan for each component.
