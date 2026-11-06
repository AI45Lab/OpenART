FROM openart/opencode:latest

LABEL maintainer="OpenART Framework"
LABEL description="OpenART runner image with goose CLI installed"
LABEL version="1.0.0"

ARG GOOSE_RELEASE_TAG=stable
ARG GOOSE_RELEASE_BASE_URL=https://github.com/aaif-goose/goose/releases/download
ARG GOOSE_ASSET=goose-x86_64-unknown-linux-gnu.tar.bz2
ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG NO_PROXY=localhost,127.0.0.1

ENV GOOSE_PROVIDER=openai
ENV GOOSE_DISABLE_KEYRING=1
ENV NO_COLOR=1
ENV PATH="/root/.local/bin:${PATH}"

# Download the release tarball directly instead of the upstream installer,
# which needs bzip2 from apt and probes GitHub's rate-limited web endpoints.
# The release base URL is configurable so builds can use a mirror.
RUN set -eux; \
    if [ -n "${HTTP_PROXY}" ]; then \
        export HTTP_PROXY HTTPS_PROXY http_proxy="${HTTP_PROXY}" https_proxy="${HTTPS_PROXY:-${HTTP_PROXY}}" \
               NO_PROXY no_proxy="${NO_PROXY:-localhost,127.0.0.1}"; \
    fi; \
    curl -fL --retry 5 --retry-all-errors \
        "${GOOSE_RELEASE_BASE_URL}/${GOOSE_RELEASE_TAG}/${GOOSE_ASSET}" \
        -o /tmp/goose.tar.bz2; \
    python3 -c "import bz2, pathlib, tarfile; tf = tarfile.open(fileobj=bz2.open('/tmp/goose.tar.bz2', 'rb'), mode='r|'); [pathlib.Path('/tmp/goose').write_bytes(tf.extractfile(m).read()) for m in tf if m.isfile() and m.name.lstrip('./') == 'goose']"; \
    test -s /tmp/goose; \
    install -d /root/.local/bin; \
    install -m 0755 /tmp/goose /root/.local/bin/goose; \
    ln -sf /root/.local/bin/goose /usr/local/bin/goose; \
    rm -f /tmp/goose /tmp/goose.tar.bz2; \
    command -v goose; \
    goose --version

WORKDIR /workspace

CMD ["/bin/bash"]