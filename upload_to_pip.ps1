# clean up
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force btc_embedded.egg-info -ErrorAction SilentlyContinue

# build distributable package
pip install build
python -m build

# upload to public repo using token prompted on command line
python -m twine upload dist/* -u __token__

# clean up
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force btc_embedded.egg-info -ErrorAction SilentlyContinue
