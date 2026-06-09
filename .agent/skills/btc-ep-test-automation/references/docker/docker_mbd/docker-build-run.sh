EP_VERSION=25.3p0
MATLAB_RELEASE=r2026a

docker build \
    --build-arg EP_RELEASE=${EP_VERSION} \
    --build-arg MATLAB_RELEASE=${MATLAB_RELEASE} \
    --tag ep_${EP_VERSION}_${MATLAB_RELEASE} \
    .

docker run --rm --volume "$(pwd):/workdir" --workdir "/workdir" \
    ep_${EP_VERSION}_${MATLAB_RELEASE} \
    run_tests.py