+++
date = 2025-08-19
title = "Betting a coffee on a socket leak"
labels = ["post"]
+++

I joined this company a while back and during my first week someone called me to take a look at a mysterious service that would start returning 502s a few days after being restarted. They were basically in a loop. Whenever it happened, someone had to go there and restart the service.

The service itself was really small, it only processed PDFs: a request arrived with an ID, the ID was used to download a PDF from AWS S3, make some changes in memory, and then upload it back to the bucket.

The team had checked everything: load balancer, database, etc. Developers even tested uploading different document sizes to confirm the problem was not caused by bigger files.

So I decided to check the code:

```
const [response, error] = await safe(async () => await this.getObject(getObjectCommandInput));
(...)
return response
```

A simple GET request to S3, but, damn it. Look at the response. We weren't consuming the damn response body. The lack of a simple `response.Body()` was causing sockets to pile up.

There are many complaints about this: [here](https://github.com/aws/aws-sdk-js-v3/issues/1959), [here](https://github.com/aws/aws-sdk-js-v3/issues/3722), [and here](https://github.com/aws/aws-sdk-js-v3/issues/6763).

The fix was boring but I was happy I found it. Even though the manager didn't believe this was the root cause - we bet a coffee and he hasn't paid me to this day (I'm still waiting, Thales). 

The response body is a stream ([Nodejs calls it a `Readable stream`](https://nodejs.org/api/stream.html#readable-streams)), and we weren't consuming it. The HTTP connections weren't being released to the connection pool, so the pool ran out of usable connections. So, yes, I was happy to solve this one out of sheer luck and a little bit of knowledge of how HTTP connections work. 
