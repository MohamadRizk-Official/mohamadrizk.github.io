"""Build assets/github-stats.json: commit activity for the portfolio's GitHub section.

Counts commits authored by USER on the default branch of every repo the token can see.
Private repos are reduced to anonymous per-day counts; their names and messages never leave
this script. When the token cannot see private repos (the default Actions token), the private
counts from the previous run are carried forward, so public numbers stay live and private
numbers never drop to zero.

env: GH_TOKEN (required), USER_LOGIN (default MohamadRizk-Official)
"""
import datetime as dt
import json
import os
import sys
import urllib.request

USER = os.environ.get("USER_LOGIN", "MohamadRizk-Official")
NAMES = {USER.lower(), "mohamad rizk"}
TOKEN = os.environ["GH_TOKEN"]
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "github-stats.json")
API = "https://api.github.com"


def get(url):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "portfolio-stats",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        link = r.headers.get("Link", "")
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                nxt = part[part.index("<") + 1:part.index(">")]
        return json.load(r), nxt


def paged(url):
    while url:
        data, url = get(url)
        yield from data


def mine(c):
    login = (c.get("author") or {}).get("login", "")
    name = c["commit"]["author"]["name"]
    return login.lower() == USER.lower() or name.lower() in NAMES


def main():
    try:
        repos = list(paged(f"{API}/user/repos?affiliation=owner&per_page=100"))
    except Exception:
        repos = []
    if not any(r["owner"]["login"].lower() == USER.lower() for r in repos):
        repos = list(paged(f"{API}/users/{USER}/repos?per_page=100"))
    repos = [r for r in repos if r["owner"]["login"].lower() == USER.lower() and not r.get("fork")]
    sees_private = any(r["private"] for r in repos)

    pub_days, priv_days, langs, recent = {}, {}, {}, []
    pub_repos = priv_repos = 0
    for r in repos:
        days = priv_days if r["private"] else pub_days
        if r["private"]:
            priv_repos += 1
        else:
            pub_repos += 1
            if r.get("language"):
                langs[r["language"]] = langs.get(r["language"], 0) + 1
        try:
            commits = [c for c in paged(f"{API}/repos/{r['full_name']}/commits?per_page=100") if mine(c)]
        except Exception as e:  # empty repo or no access
            print("skip", r["name"], e, file=sys.stderr)
            continue
        for c in commits:
            d = c["commit"]["author"]["date"][:10]
            days[d] = days.get(d, 0) + 1
        for c in commits[:15]:
            recent.append({
                "repo": None if r["private"] else r["name"],
                "url": None if r["private"] else c["html_url"],
                "message": None if r["private"] else c["commit"]["message"].splitlines()[0][:110],
                "date": c["commit"]["author"]["date"],
            })

    prev = {}
    if os.path.exists(OUT):
        prev = json.load(open(OUT))
    if not sees_private:
        priv_days = prev.get("privateDays", {})
        priv_repos = prev.get("privateRepos", 0)
        recent += [x for x in prev.get("recent", []) if x["repo"] is None]

    all_days = dict(pub_days)
    for d, n in priv_days.items():
        all_days[d] = all_days.get(d, 0) + n

    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=364 + (today.weekday() + 1) % 7)  # calendar starts on a Sunday
    year = [{"d": (start + dt.timedelta(days=i)).isoformat(), "n": all_days.get((start + dt.timedelta(days=i)).isoformat(), 0)}
            for i in range((today - start).days + 1)]

    active = sorted(d for d, n in all_days.items() if n)
    longest = run = 0
    prev_day = None
    for d in active:
        cur = dt.date.fromisoformat(d)
        run = run + 1 if prev_day and (cur - prev_day).days == 1 else 1
        longest = max(longest, run)
        prev_day = cur
    current = 0
    day = today if all_days.get(today.isoformat()) else today - dt.timedelta(days=1)
    while all_days.get(day.isoformat()):
        current += 1
        day -= dt.timedelta(days=1)

    recent.sort(key=lambda x: x["date"], reverse=True)
    out = {
        "user": USER,
        "updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "totalCommits": sum(all_days.values()),
        "yearCommits": sum(x["n"] for x in year),
        "activeDays": len(active),
        "longestStreak": longest,
        "currentStreak": current,
        "publicRepos": pub_repos,
        "privateRepos": priv_repos,
        "busiestDay": max(year, key=lambda x: x["n"]) if year else None,
        "languages": sorted(langs.items(), key=lambda kv: -kv[1]),
        "year": year,
        "recent": recent[:40],
        "privateDays": priv_days,
    }
    if prev and {k: v for k, v in prev.items() if k != "updated"} == {k: v for k, v in out.items() if k != "updated"}:
        print("no change")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)
    print("commits", out["totalCommits"], "year", out["yearCommits"], "private access", sees_private)


if __name__ == "__main__":
    main()
