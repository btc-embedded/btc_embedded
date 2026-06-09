EP_VERSION=25.3p0

docker build \
    --build-arg EP_VERSION=${EP_VERSION} \
    --tag ep_${EP_VERSION} \
    .

docker run --rm --volume "$(pwd):/workdir" --workdir "/workdir" \
    ep_${EP_VERSION} \
    python3 run_tests.py
