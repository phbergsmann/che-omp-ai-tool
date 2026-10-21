FROM registry.access.redhat.com/hi/core-runtime:2.43-builder@sha256:51c7bc493a1bd04bc1ba0010b232fe42dd3885a587c8d692adbff22a3ba9b7f5 AS fetch
ARG OMP_VERSION
ARG TARGETARCH
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
USER 0:0
WORKDIR /artifacts
RUN chown 65532:0 /artifacts
USER 65532:0
RUN set -eu; \
    test -n "$OMP_VERSION"; \
    case "$OMP_VERSION" in v[0-9]*.[0-9]*.[0-9]*) ;; *) exit 1 ;; esac; \
    arch="${TARGETARCH:-$(uname -m)}"; \
    case "$arch" in amd64|x86_64) asset=omp-linux-x64 ;; arm64|aarch64) asset=omp-linux-arm64 ;; *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; esac; \
    base="https://github.com/can1357/oh-my-pi/releases/download/$OMP_VERSION"; \
    curl --fail --location --retry 3 "$base/$asset" --output "$asset"; \
    curl --fail --location --retry 3 "$base/SHA256SUMS.txt" --output SHA256SUMS.txt; \
    line=$(grep -E "^[0-9a-fA-F]{64} [ *]${asset}$" SHA256SUMS.txt); \
    test "$(printf '%s\n' "$line" | wc -l)" -eq 1; \
    printf '%s\n' "$line" | sha256sum --check --strict -; \
    mv "$asset" omp; chmod 0755 omp; \
    mkdir notices; \
    for file in LICENSE THIRD-PARTY-NOTICES.txt; do \
      curl --fail --location --retry 3 "https://raw.githubusercontent.com/can1357/oh-my-pi/$OMP_VERSION/$file" --output "notices/$file"; \
    done; \
    curl --fail --location --retry 3 "https://raw.githubusercontent.com/can1357/oh-my-pi/$OMP_VERSION/packages/natives/THIRD-PARTY-NOTICES.txt" --output notices/NATIVE-THIRD-PARTY-NOTICES.txt

FROM registry.access.redhat.com/hi/core-runtime:2.43@sha256:1dc3435a7fd02540d25657bc2dd9723b70a87467fd49b29661b819bb96e626a1
ARG OMP_VERSION
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="OMP Che AI tool injector" \
      org.opencontainers.image.description="Standalone upstream OMP executable for Eclipse Che init injection" \
      org.opencontainers.image.source="https://github.com/phbergsmann/che-omp-ai-tool" \
      org.opencontainers.image.version="${OMP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="MIT AND LicenseRef-Upstream-Third-Party" \
      io.github.phbergsmann.omp.version="${OMP_VERSION}" \
      io.github.phbergsmann.omp.source="https://github.com/can1357/oh-my-pi"
USER 0:0
RUN mkdir -p /home/omp /projects && chgrp -R 0 /home/omp /projects && chmod -R g=u /home/omp /projects
COPY --from=fetch /artifacts/omp /usr/local/bin/omp
COPY --from=fetch /artifacts/notices/ /usr/share/licenses/omp/
COPY --from=fetch /artifacts/SHA256SUMS.txt /usr/share/omp/SHA256SUMS.txt
ENV HOME=/home/omp
WORKDIR /projects
USER 10001:0
ENTRYPOINT ["/usr/local/bin/omp"]
CMD ["--help"]
