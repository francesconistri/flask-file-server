BIN_DIR ?= venv/bin

start: build
	$(BIN_DIR)/python file_server.py

dev: build
	FLASK_DEBUG=1 FLASK_APP=file_server.py $(BIN_DIR)/flask run --port=8000

build:
	$(BIN_DIR)/pip install -U pip
	$(BIN_DIR)/pip install -r requirements.txt
	$(BIN_DIR)/pip install -r dev-requirements.txt

.PHONY: start dev
