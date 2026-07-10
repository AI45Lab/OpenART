FROM openart/opencode:latest

LABEL maintainer="OpenART Framework"
LABEL description="OpenART runner image with goose CLI installed"
LABEL version="1.0.0"

ARG GOOSE_RELEASE_TAG=stable
ARG GOOSE_VERSION=

ENV GOOSE_PROVIDER=openai
ENV GOOSE_DISABLE_KEYRING=1
ENV NO_COLOR=1
ENV PATH="/root/.local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends bzip2 \
    && rm -rf /var/lib/apt/lists/* \
    && if [ -n "${GOOSE_VERSION}" ]; then \
        curl -fsSL https://github.com/aaif-goose/goose/releases/download/${GOOSE_RELEASE_TAG}/download_cli.sh | CONFIGURE=false GOOSE_VERSION="${GOOSE_VERSION}" bash; \
    else \
        curl -fsSL https://github.com/aaif-goose/goose/releases/download/${GOOSE_RELEASE_TAG}/download_cli.sh | CONFIGURE=false bash; \
    fi \
    && command -v goose \
    && ln -sf "$(command -v goose)" /usr/local/bin/goose \
    && goose --version

WORKDIR /workspace

CMD ["/bin/bash"]
