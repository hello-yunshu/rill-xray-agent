# Rill Xray Agent PID1 qualification image.
# systemd is the real init (PID 1); the frozen canonical payload (with the
# best-effort RillML prebuilt runtime install) is installed inside and the
# pid1-rillml suite runs against it. All qualification is Docker-only.
ARG BASE=debian:12
FROM ${BASE}
ENV container=docker
RUN apt-get update && apt-get install -y --no-install-recommends \
      systemd systemd-sysv bash jq curl python3 ca-certificates psmisc \
      gettext-base iproute2 net-tools procps openssl unzip \
    && rm -rf /var/lib/apt/lists/*
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
