.PHONY: dev
dev:
	osascript -e 'tell app "Terminal" to do script "cd $(PWD) && poetry run uvicorn src.server:app --reload --host 0.0.0.0 --port 8000"'
	osascript -e 'tell app "Terminal" to do script "redis-server"'
	osascript -e 'tell app "Terminal" to do script "cd $(PWD) && poetry run celery -A src.services.celery.celery_app worker --loglevel=info --pool=threads"'