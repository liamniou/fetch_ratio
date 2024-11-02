Fetch values from target URL by selectors and expose as Prometheus metrics.

## Build

```
go mod download
go build -o fetch_ratio
```

###

## Run
```
export PROFILE_URL=...
export USER_AGENT=...
export COOKIE_STRING=...
export DL_ELEMENT_SELECTOR=...
export UL_ELEMENT_SELECTOR=...
./fetch_ratio
```

## Example compose
```
services:
  exporter:
    image: fetch_ratio:latest
    container_name: exporter
    restart: unless-stopped
    ports:
      - 17501:17501
    environment:
      - EXPORTER_PORT=17501
      - PROFILE_URL=...
      - COOKIE_STRING=...
      - USER_AGENT=...
      - DL_ELEMENT_SELECTOR=#body > tbody > tr > td > center > center > table > tbody > tr:nth-child(8) > td
      - UL_ELEMENT_SELECTOR=#body > tbody > tr > td > center > center > table > tbody > tr:nth-child(7) > td
```
