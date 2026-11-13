.PHONY: e1 test

e1:
	python src/e1/pipeline.py

test:
	python -m pytest -q
