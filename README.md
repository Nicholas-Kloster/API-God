# API-God

API-God is a free X (Twitter) intelligence tool. 
Core function: give it any search term (topic, person, company, ticker, hashtag, event) and it returns a structured list of who on 
X is posting about it, what they said, and engagement numbers, sortable and saveable.

The point is doing this without X's paid API, which runs tens of thousands a month for this access tier.
  
Find who's talking about anything on X (Twitter), for free. No API key. No $30,000-a-month data bill.

## What it does

Give it a search: a topic, a person, a company, a coin, a hashtag, an event, anything. It finds the
people on X posting about it and hands you a clean list: who they are, what they said, and how much
engagement each post got. Sortable, saveable, structured.

It does this without X's paid API, which costs tens of thousands of dollars a month for this kind of
access.

## The tool: xsearch

```
cd search
pip install -r requirements.txt
python xsearch.py --login          # one-time login, for the free backend
python xsearch.py "any topic"      # then search anything
python xsearch.py '$TICKER'
python xsearch.py "a person or company"
```

Three ways to run it:

- **session**: free. Uses your own X login.
- **xai**: about half a cent per search. No login, no account risk (needs an xAI key).
- **both**: runs the two together and merges the results.

Full guide: `search/README.md`.

## How it works

Two free pieces, glued together.

1. **Finding posts.** To find who is posting about something, the tool either drives X's own search
   through your logged-in session (the `session` backend) or asks xAI's search service (the `xai`
   backend). Either way it ends up with a set of post links.
2. **Reading posts.** Each post is read through `cdn.syndication.twimg.com`, the public endpoint that
   powers embedded tweets across the web. It returns a post's text, author, and engagement as clean
   JSON, with no login and no key. That is the part that makes it free.

Find the posts, then read each one through the free public endpoint. No paid X API anywhere in the loop.

## Where the idea came from

The data you want, who is saying what on X, sits behind X's official API. That API costs tens of
thousands of dollars a month at the volume you would actually need.

You do not need it. X already hands the same data out for free in two places. Its own web app reads
posts through endpoints that work as long as you are logged in, no key. And every tweet embedded on any
website is served by a public endpoint that needs no login at all. Both were sitting in plain sight.

We tested the idea on the noisiest thing we could find: the flood of new Solana coins minting every
minute, each with an X link attached. The free path worked end to end, find the posts, read them through
the public endpoint, all for free. Then the obvious part, the same find-and-read works for anything: a
person, a company, an event, not just coins. That is the tool.

## One example of what you can build on it: a Solana coin tracker

`engine/` is a prototype that points the same idea at one specific use. It watches new Solana coins the
moment they launch, finds the X account behind each, and ranks them. It is an **example**, one
application of the search tool, not the purpose of the project. The search tool is the general thing.

## Layout

```
search/   xsearch: find who's talking about anything on X
engine/   example app: a Solana coin-tracking prototype built on the same idea
legacy/   retired Node browser-capture tool
docs/     design notes
```
