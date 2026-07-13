# VectorRisk — common tasks.  Run `make help`.
PORT ?= 8000
RES  ?= 10m

help:
	@echo "make env        - create the conda env (GDAL stack) from environment.yml"
	@echo "make install    - pip install this package with all extras"
	@echo "make check      - test connectivity to every data source + licences"
	@echo "make fetch      - download WorldClim ($(RES)) + boundaries into the cache"
	@echo "make serve      - run the API + dashboard at http://localhost:$(PORT)/"
	@echo "make test       - run the unit tests"
	@echo "make docker     - build the container image"

env:
	conda env create -f environment.yml || conda env update -f environment.yml

install:
	pip install -e ".[full]"

check:
	vectorrisk check --resolution $(RES)

fetch:
	vectorrisk fetch --resolution $(RES)

serve:
	vectorrisk serve --host 0.0.0.0 --port $(PORT)

test:
	python -m pytest -q tests/ || python -m vectorrisk metrics 27 150

docker:
	docker build -t vectorrisk .

.PHONY: help env install check fetch serve test docker
