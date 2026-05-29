# API-God

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

| Backend | Cost | Needs | Account risk |
|---------|------|-------|--------------|
| `session` | Free | Your own X login | Yes. Drives your logged-in account, so heavy use can get it rate-limited or suspended. |
| `xai` | ~$0.005 per search | An xAI key | None. No X login, nothing tied to your account. |
| `both` | Sum of the two | Both of the above | Same as `session`, since it runs that path too. |

> **Warning: the `session` and `both` backends can get your X account suspended.** They drive your own
> logged-in account through X's web search. Heavy or fast use looks like automation and X can
> rate-limit or ban the account. The `xai` backend carries no such risk: it uses no X login.

Pick `session` to pay nothing and accept the account risk. Pick `xai` to pay half a cent and carry no
risk. Pick `both` when you want the widest result set and have already accepted the `session` risk.

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

### Why those endpoints stay open

X gates this data behind the paid API, but it cannot close the two free doors without breaking its own
product. The logged-in web endpoints are what x.com itself runs on. Kill them and the website dies. The
syndication endpoint at `cdn.syndication.twimg.com` renders embedded tweets on every news site, blog,
and forum. Kill it and tweet embeds break everywhere. The data leaks through the parts of X that have to
stay public. The tool reads the same doors the browser already uses.

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
