.PHONY: check test smoke build accept clean

check:
	python scripts/check.py

test:
	python -m unittest discover -s tests -v

smoke:
	python scripts/smoke_test.py

build:
	python scripts/build_zipapp.py
	python -m pip wheel . --no-deps -w dist/wheel

accept: check test smoke build
	python dist/savedelta.pyz --version

clean:
	python -c "import shutil; [shutil.rmtree(path, ignore_errors=True) for path in ('build', 'dist')]"
