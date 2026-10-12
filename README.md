# URL Shortener

A local URL shortener implemented with Python 3.13's standard library only. It creates random persistent IDs in a JSON file and serves real HTTP 302 redirects. It never uses an external shortening service. URLs are validated as absolute HTTP(S) links, credentials are rejected, and the server binds to `127.0.0.1` by default.

## Run

```powershell
py -3.13 url_shortener.py
```

Open <http://127.0.0.1:8000>, paste an HTTP(S) URL, and submit. The created short link redirects to its saved destination. Stop the server with Ctrl+C. Persistent data is stored outside this project at `%USERPROFILE%\.url-shortener\urls.json` by default; override with `--database` or change the local port with `--port`.

To listen on a LAN interface, pass an explicit `--host` such as `0.0.0.0`; this is not recommended for untrusted networks.

## Test

```powershell
py -3.13 -m unittest discover -s tests -v
```