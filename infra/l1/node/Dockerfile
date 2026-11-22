# AvalancheGo + Subnet-EVM for the ZyrcleChain validator.
# Base pinned by digest: avaplatform/subnet-evm:v1.15.3 (AvalancheGo v1.15.3, plugin version 47).
FROM avaplatform/subnet-evm:v1.15.3@sha256:17dab2a8af16ae6adcc51ec7b2d6cd2314b31de4d6ae1188e51a8d229afd2b45

# The chain uses the standard Subnet-EVM VM ID (srEXiWaHuhNyGwPUi444Tu47ZEDwxTWrbQiuD7FmgSAQ6X7Dy),
# whose plugin ships in the base image.
RUN groupadd --system --gid 10001 avalanche \
 && useradd --system --uid 10001 --gid avalanche --home-dir /data --shell /usr/sbin/nologin avalanche \
 && mkdir -p /data && chown avalanche:avalanche /data

USER avalanche
WORKDIR /avalanchego/build
ENTRYPOINT ["./avalanchego", "--config-file=/config/node.json"]
