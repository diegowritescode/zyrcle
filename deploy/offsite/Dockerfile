# The two tools of the off-site copy (docs/adr/0034): age encrypts, rclone uploads. Built on the VPS
# by offsite.sh, so nothing is installed on the host itself.
FROM alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f
RUN apk add --no-cache age rclone ca-certificates
USER 65534:65534
ENTRYPOINT []
