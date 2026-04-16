PYTHON ?= python3

.PHONY: test ci

test:
	$(PYTHON) -m tests

ci: test
