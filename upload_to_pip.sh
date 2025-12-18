# clean up
rm -rf build dist btc_embedded.egg-info

# build distributable package
pip install build
python3 -m build

# upload to public repo using token from keychain
python3 -m twine upload dist/* -u __token__

# clean up
rm -rf build dist btc_embedded.egg-info
