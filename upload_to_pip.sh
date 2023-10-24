# build distributable package
python3 setup.py sdist

# upload to public repo using token from keychain
twine upload dist/* -u __token__

# clean up
rm -rf dist