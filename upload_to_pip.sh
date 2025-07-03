# clean up
rm -rf build dist btc_embedded.egg-info

# build distributable package
python3 setup.py sdist bdist_wheel

# upload to public repo using token from keychain
python3 -m twine upload dist/* -u __token__

# clean up
rm -rf build dist btc_embedded.egg-info
