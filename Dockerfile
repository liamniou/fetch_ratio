FROM golang:1.22.5-bullseye AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN go build -mod=readonly -v -o /bin/fetch_ratio ./main.go

FROM debian:bullseye-slim
RUN set -x && apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

COPY --from=builder /bin/fetch_ratio /fetch_ratio

CMD ["/fetch_ratio"]
