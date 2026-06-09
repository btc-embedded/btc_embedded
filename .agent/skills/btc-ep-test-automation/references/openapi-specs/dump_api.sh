EP_VERSION=26.1p0-beta

echo ""
echo ">>> Dumping API spec for EP version ${EP_VERSION}"

docker build \
    --build-arg EP_VERSION=${EP_VERSION} \
    --tag ep_${EP_VERSION} \
    .

docker run --rm --volume "$(pwd):/workdir" --workdir "/workdir" \
    ep_${EP_VERSION} \
    python3 dump_api.py ${EP_VERSION}
