PY ?= python
LAKE ?= lake

.PHONY: setup backfill daily rebuild replay charts test lint validate-infra cost

setup:            ## virtualenv with dev dependencies
	$(PY) -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

backfill:         ## every year since 1976 from s3://noaa-gsod-pds (anonymous, ~1 minute)
	$(PY) -m barsha --lake $(LAKE) run --backfill

daily:            ## what the scheduled job does: this year and last year, incremental
	$(PY) -m barsha --lake $(LAKE) run

rebuild:          ## rebuild silver and gold from raw/ without touching the source
	$(PY) -m barsha --lake $(LAKE) rebuild

replay:           ## the bulletin for 28 September 2024, the Kathmandu flood
	$(PY) -m barsha --lake $(LAKE) bulletin --as-of 2024-09-28

charts:           ## docs/img from the local lake
	PYTHONPATH=. $(PY) scripts/make_charts.py --lake $(LAKE)

cost:             ## monthly cost model behind docs/COST.md
	$(PY) scripts/cost_model.py

test:
	$(PY) -m pytest -q

lint:
	ruff check .

validate-infra:   ## lint the SAM/CloudFormation template
	cfn-lint infra/template.yaml
