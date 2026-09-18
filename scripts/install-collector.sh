#!/bin/sh
# Pinned official Collector distribution; downloads only when not installed.
set -eu
VERSION=0.161.0
DESTINATION=${1:?Usage: install-collector.sh DESTINATION}
case "$(uname -m)" in
    arm64) ARCH=arm64; SHA=ccc0cf5de5242adcaedc7b5aebed43a1dc56aa2dc7de6ebc495d5db60512d34c ;;
    x86_64) ARCH=amd64; SHA=357fc0a7a77f5d42cab2f46af6be301062a7824b82454cc264cb8661fa9a8734 ;;
    *) echo "Unsupported architecture" >&2; exit 1 ;;
esac
if [ -x "$DESTINATION" ] && "$DESTINATION" --version | grep -q "$VERSION"; then
    exit 0
fi
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT HUP INT TERM
ARCHIVE="otelcol-contrib_${VERSION}_darwin_${ARCH}.tar.gz"
curl --fail --location --retry 2 \
    "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v$VERSION/$ARCHIVE" \
    -o "$WORK/collector.tar.gz"
ACTUAL=$(shasum -a 256 "$WORK/collector.tar.gz" | cut -d ' ' -f 1)
[ "$ACTUAL" = "$SHA" ] || { echo "Collector checksum mismatch" >&2; exit 1; }
tar -xzf "$WORK/collector.tar.gz" -C "$WORK" otelcol-contrib
mkdir -p "$(dirname "$DESTINATION")"
install -m 755 "$WORK/otelcol-contrib" "$DESTINATION"
