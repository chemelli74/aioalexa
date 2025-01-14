# SPDX-License-Identifier: Apache-2.0
# Based on code from https://github.com/bachya/simplisafe-python/blob/dev/Makefile
coverage:
	#Not implemented yet
	#poetry run py.test -s --verbose --cov-report term-missing --cov-report xml --cov=alexapy tests
bump:
	poetry run semantic-release release
	poetry run semantic-release changelog
bump_and_publish:
	poetry run semantic-release publish
check_vulns:
	poetry run safety check
clean:
	rm -rf dist/ build/ .egg alexapy.egg-info/
init: setup_env
	poetry install
lint: black flake8 docstyle pylint typing
flake8:
	poetry run flake8 alexapy
docstyle:
	poetry run pydocstyle alexapy
pylint:
	poetry run pylint alexapy
black:
	poetry run black alexapy
docs: docstyle
	poetry export --dev --without-hashes -f requirements.txt --output docs/requirements.txt
	echo "alexapy" >> docs/requirements.txt
	poetry run sphinx-build -b html docs docs/html
# publish:
# deprecated by semantic-release
# 	poetry run python setup.py sdist bdist_wheel
# 	poetry run twine upload dist/*
# 	rm -rf dist/ build/ .egg alexapy.egg-info/
setup_env:
	pip install poetry
test:
	#Not implemented yet
	#poetry run py.test
typing:
	poetry run mypy --ignore-missing-imports alexapy
